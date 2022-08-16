#!/usr/bin/python3

import sys
import os
from time import sleep
from datetime import datetime
from copy import copy
import argparse
import re
import threading
import queue
from subprocess import check_output, STDOUT
from pathlib import Path
import json
import csv

from influxdb_logger import Influxdb_logger
from ping_tool import Ping_runner
from iperf3_tool import Iperf3_runner


class Wifi_test_logger(Influxdb_logger):

    def __init__(self, duration, router_ip, location, iperf_server_ip, reverse, no_iperf):
        super().__init__()
        self.duration = duration
        self.location = location
        self.router_ip = router_ip
        self.iperf_server_ip = iperf_server_ip
        self.reverse = reverse
        self.no_iperf = no_iperf
        self.lost_msg_showed = False

        self.total_signal = 0
        self.total_latency = 0
        self.total_throughput = 0

        self.summary_folder = Path.cwd().joinpath('summary')
        if not self.summary_folder.exists():
            self.summary_folder.mkdir()

        self.log_file = self.log_folder.joinpath(
            f'log_wifi_test_{datetime.now().date()}')

        self.summary_file = self.summary_folder.joinpath(
            f'{datetime.now().date()}_wifi_test_summary')

        self.summary_csv_file = self.summary_folder.joinpath(
            f'{datetime.now().date()}_wifi_test_summary.csv')

        self.queue_ping = queue.Queue()
        self.queue_iperf = queue.Queue()

    def get_wifi_link_status(self):
        # iw info
        cmd = 'iw wlo1 info'
        # print(f'==> cmd send: \n\n\t{cmd}\n')

        cmd_result = check_output(
            [cmd], timeout=3, stderr=STDOUT, shell=True).decode('utf8').strip()
        # print(cmd_result)

        # get ssid
        ssid_pattern = re.compile(r'ssid (.*)')
        self.ssid = ssid_pattern.search(cmd_result).group(1)
        # print(self.ssid)

        # get channel
        channel_pattern = re.compile(r'channel ([^,]*),')
        self.channel = channel_pattern.search(cmd_result).group(1)
        # print(self.channel)

        # get bandwidth
        bandwidth_pattern = re.compile(r'width: (\d*) MHz')
        self.bandwidth = int(bandwidth_pattern.search(cmd_result).group(1))
        # print(self.bandwidth)

        # get center freq
        center_freq_pattern = re.compile(r'center1: (\d*) MHz')
        self.center_freq = int(center_freq_pattern.search(cmd_result).group(1))
        if self.center_freq < 3000:
            print('\n==> Connect Wifi to 2.4 GHz.\n')
            self.connected_at_5GHz = False
        else:
            print('\n==> Connect Wifi to 5 GHz.\n')
            self.connected_at_5GHz = True

        sleep(2)

    def detect_signal(self, duration):
        '''
        show collected result from ping and iperf thread and send to buffer
        '''
        cmd = 'iw wlo1 link'

        for sec, _ in enumerate(range(duration), start=1):
            cmd_result = check_output(
                [cmd], timeout=5, stderr=STDOUT, shell=True).decode('utf8').strip()

            if cmd_result == 'Not connected.':
                if not self.lost_msg_showed:
                    print('==> wifi connection lost.')
                    self.lost_msg_showed = True
                sleep(1)
                continue

            # output difference from iw wlo1 link
            # wifi 5
            # rx bitrate: 58.5 Mbit/s VHT-MCS 9 80 MHz VHT-NSS 1
            # wifi 6
            # rx bitrate: 1200.9 MBit/s 80MHz HE-MCS 11 HE-NSS 2 HE-GI 0 HE-DCM 0
            # 2.4 GHz
            # rx bitrate: 144.4 MBit/s MCS 15 short GI

            # get rx bitrate
            bitrate_pattern = re.compile(r'rx bitrate: (.*) MBit/s')
            try:
                rx_bitrate = float(bitrate_pattern.search(cmd_result).group(1))
            except AttributeError:
                if not self.lost_msg_showed:
                    print('==> missing essential value: rx bitrate.')
                    print(cmd_result)
                sleep(1)
                continue

            # get tx bitrate
            bitrate_pattern = re.compile(r'tx bitrate: (.*) MBit/s')
            try:
                tx_bitrate = float(bitrate_pattern.search(cmd_result).group(1))
            except AttributeError:
                if not self.lost_msg_showed:
                    print('==> missing essential value: tx bitrate.')
                    print(cmd_result)
                sleep(1)
                continue

            # get rx mcs
            rx_mcs_pattern = re.compile(r'rx.*(HE-MCS|VHT-MCS|MCS) (\d*)\W')
            try:
                rx_mcs = int(rx_mcs_pattern.search(cmd_result).group(2))
            except (AttributeError, ValueError):
                # if connected to 2.4GHz, sometimes there is no rx mcs showed in cmd output.
                if not self.connected_at_5GHz:
                    tx_mcs = 0
                else:
                    if not self.lost_msg_showed:
                        print('==> missing essential value: rx mcs.')
                        print(cmd_result)
                    sleep(1)
                    continue

            # get tx mcs
            tx_mcs_pattern = re.compile(r'tx.*(HE-MCS|VHT-MCS|MCS) (\d*)\W')
            try:
                tx_mcs = int(tx_mcs_pattern.search(
                    cmd_result).group(2).strip())
            except (AttributeError, ValueError):
                # if connected to 2.4GHz, sometimes there is no tx mcs showed in cmd output.
                if not self.connected_at_5GHz:
                    tx_mcs = 0
                else:
                    if not self.lost_msg_showed:
                        print('==> missing essential value: tx mcs.')
                        print(cmd_result)
                    sleep(1)
                    continue

            # get nss
            # when connect to 2.4GHz there is no nss info in iw link output
            nss_pattern = re.compile(r'(HE-NSS|VHT-NSS) (\d*)\W')
            if not self.connected_at_5GHz:
                nss = 0
            else:
                try:
                    nss = int(nss_pattern.search(cmd_result).group(2))
                except AttributeError:
                    if not self.lost_msg_showed:
                        print('==> missing essential value: nss.')
                        print(cmd_result)
                    sleep(1)
                    continue

            # get signal
            signal_pattern = re.compile(r'signal: (.*) dBm')
            try:
                signal = int(signal_pattern.search(cmd_result).group(1))
            except AttributeError:
                if not self.lost_msg_showed:
                    print('==> missing essential value.')
                sleep(1)
                continue

            # get ping latency from ping_tool
            try:
                latency = self.queue_ping.get(timeout=3)
                self.queue_ping.task_done()
            except queue.Empty:
                if not self.lost_msg_showed:
                    print('==> Error: cannot get ping result from queue.')
                sleep(1)
                continue

            # get iperf throughput from iperf3_tool
            if not self.no_iperf:
                try:
                    throughput = self.queue_iperf.get(timeout=1)
                    self.queue_iperf.task_done()
                except queue.Empty:
                    if not self.lost_msg_showed:
                        print('==> Error: cannot get iperf result from queue.')
                    sleep(1)
                    continue
            else:
                throughput = 0.0

            print(
                f'sec: {sec}, ssid: {self.ssid}, channel: {self.channel}, bandwidth: {self.bandwidth}')
            print(
                f'\tsignal: {signal} dBm. Rx_bitrate: {rx_bitrate} Mbit/s, Tx_bitrate: {tx_bitrate} Mbit/s, rx_mcs: {rx_mcs}, tx_mcs: {tx_mcs}, nss: {nss}.')
            print(f'\tlatency: {latency} ms, throughput: {throughput} Mbps')
            print('-' * 120)

            record_time = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            data = {
                'measurement': 'wifi_test',
                'time': record_time,
                'fields': {'location': self.location,
                           'ssid': self.ssid,
                           'channel': self.channel,
                           'bandwidth': self.bandwidth,
                           'signal': signal,
                           'rx_bitrate': rx_bitrate,
                           'tx_bitrate': tx_bitrate,
                           'rx_mcs': rx_mcs,
                           'tx_mcs': tx_mcs,
                           'nss': nss,
                           'latency': latency,
                           'throughput': throughput
                           }
            }

            self.logging_with_buffer(data)

            self.total_signal += signal
            self.total_latency += latency
            self.total_throughput += throughput

            self.lost_msg_showed = False
            sleep(1)

    def start_ping(self):
        # set ping tos = 240 to use high priority
        ping_runner = Ping_runner(ip=self.router_ip, tos=240, duration=self.duration,
                                  interval=1, queue=self.queue_ping)
        self.ping_summary = ping_runner.run()

        # show summary
        # print(f'{self.ping_summary=}')

        # get and show ping mdev
        mdev_pattern = re.compile(r'/([0-9.]*) ms')
        self.latency_mdev = float(
            mdev_pattern.search(self.ping_summary).group(1))
        print(f'{self.latency_mdev=}')

        # get packet loss rate stuff
        packet_sent_pattern = re.compile(r'([0-9]*) packets transmitted')
        self.packet_sent = int(
            packet_sent_pattern.search(self.ping_summary).group(1))
        print(f'{self.packet_sent=}')

        packet_received_pattern = re.compile(r'([0-9]*) received')
        self.packet_received = int(
            packet_received_pattern.search(self.ping_summary).group(1))
        print(f'{self.packet_received=}')

        loss_rate_pattern = re.compile(r'([0-9.]*)% packet loss')
        self.packet_loss_rate = float(
            loss_rate_pattern.search(self.ping_summary).group(1))
        print(f'{self.packet_loss_rate=}%')

    def start_iperf(self):
        iperf_runner = Iperf3_runner(host=self.iperf_server_ip, tos=0, port=5201, exec_secs=self.duration,
                                     bitrate=0, udp=False, reverse=self.reverse, buffer_length=1024,
                                     queue=self.queue_iperf)
        iperf_runner.run()

    def summarize(self):
        self.summary = {}
        self.summary['time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self.summary['location'] = self.location
        self.summary['ssid'] = self.ssid
        self.summary['channel'] = self.channel
        self.summary['bandwidth'] = self.bandwidth
        self.summary['avg_signal'] = self.avg_signal
        self.summary['avg_latency'] = self.avg_latency
        self.summary['avg_throughput'] = self.avg_throughput
        self.summary['latency_mdev'] = self.latency_mdev
        self.summary['duration'] = self.duration
        self.summary['tput_direction'] = 'dl' if self.reverse else 'ul'

    def summarize_to_file(self):
        with open(self.summary_file, 'a') as f:
            f.write(json.dumps(self.summary))
            f.write('\n')

    def summarize_to_csv(self):
        headers = ['time', 'location', 'ssid', 'channel', 'bandwidth',  'avg_signal',
                   'avg_latency', 'latency_mdev', 'tput_direction', 'avg_throughput', 'duration']

        if not self.summary_csv_file.exists():
            with open(self.summary_csv_file, 'w', encoding='utf_8') as csv_file:
                writer = csv.DictWriter(csv_file, fieldnames=headers)
                writer.writeheader()

        with open(self.summary_csv_file, 'a', encoding='utf_8') as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=headers)
            writer.writerow(self.summary)

    def show_avg(self):
        self.avg_signal = round(self.total_signal / self.duration, 2)
        self.avg_latency = round(self.total_latency / self.duration, 2)
        self.avg_throughput = round(self.total_throughput / self.duration, 2)

        print('=' * 120)
        print(f'Avg signal: {self.avg_signal} dBm.')
        print(f'Avg latency: {self.avg_latency} ms.')
        print(f'Avg throughput: {self.avg_throughput} Mbit/s.')
        print('=' * 120)

    def run(self):
        self.get_wifi_link_status()

        th = threading.Thread(target=self.start_ping, daemon=True)
        th.start()

        if not self.no_iperf:
            th = threading.Thread(target=self.start_iperf, daemon=True)
            th.start()

        # wait ping and iperf thread to start and put data in queue
        sleep(2)

        self.detect_signal(self.duration)

        self.show_avg()

        self.clean_buffer_and_send()

        self.summarize()
        self.summarize_to_file()
        self.summarize_to_csv()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-l', '--location', metavar='', required=True, type=str,
                        help='tag data with location')
    parser.add_argument('-t', '--duration', metavar='', default=300, type=int,
                        help='test time duration (secs)')
    parser.add_argument('-r', '--router_ip', metavar='', default='192.168.50.1', type=str,
                        help='router\'s IP')
    parser.add_argument('-s', '--iperf_server_ip', metavar='', default='192.168.50.210', type=str,
                        help='iperf3\'s server IP')
    parser.add_argument('-R', '--reverse', action="store_true",
                        help='iperf direction reverse to downlink from server')
    parser.add_argument('-N', '--no_iperf', action="store_true",
                        help='disable iperf test.')

    args = parser.parse_args()
    logger = Wifi_test_logger(duration=args.duration, iperf_server_ip=args.iperf_server_ip, no_iperf=args.no_iperf,
                              router_ip=args.router_ip, reverse=args.reverse, location=args.location)

    try:
        logger.run()
    except KeyboardInterrupt:
        print('\n==> Interrupted.\n')
        logger.clean_buffer_and_send()
        sleep(0.1)
        max_sec_count = logger.db_retries * logger.db_timeout
        countdown = copy(max_sec_count)
        while logger.is_sending:
            if countdown < max_sec_count:
                print(
                    f'==> waiting for process to end ... secs left max {countdown}')
            countdown -= 1
            sleep(1)
        try:
            print('\n==> Exited')
            sys.exit(0)
        except SystemExit:
            os._exit(0)
    # except Exception as e:
    #     print(f'==> wifi_logger_runner error: {e.__class__} {e}')
