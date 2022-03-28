#!/usr/bin/python3

import sys
import os
from time import sleep
from datetime import datetime
from copy import copy
import argparse
import re
import pexpect
from subprocess import check_output, STDOUT


class Wifi_test_logger:

    def __init__(self):
        pass

    def get_wifi_link_status(self):
        # iw info
        cmd = 'iw wlo1 info'
        # print(f'==> cmd send: \n\n\t{cmd}\n')

        cmd_result = check_output(
            [cmd], timeout=3, stderr=STDOUT, shell=True).decode('utf8').strip()
        print(cmd_result)

        # get ssid
        ssid_pattern = re.compile(r'ssid (.*)')
        self.ssid = ssid_pattern.search(cmd_result).group(1)
        print(self.ssid)

        # get channel
        channel_pattern = re.compile(r'channel ([^,]*),')
        self.channel = channel_pattern.search(cmd_result).group(1)
        print(self.channel)

        # get bandwidth
        bandwidth_pattern = re.compile(r'width: (\d*) MHz')
        self.bandwidth = bandwidth_pattern.search(cmd_result).group(1)
        print(self.bandwidth)

        ####################################################################
        # iw link
        cmd = 'iw wlo1 link'
        # print(f'==> cmd send: \n\n\t{cmd}\n')

        cmd_result = check_output(
            [cmd], timeout=3, stderr=STDOUT, shell=True).decode('utf8').strip()
        print(cmd_result)

    def detect_signal(self, sec_to_test):
        cmd = 'iw wlo1 link'
        total = 0

        for sec, _ in enumerate(range(sec_to_test), start=1):
            cmd_result = check_output(
                [cmd], timeout=5, stderr=STDOUT, shell=True).decode('utf8').strip()

            if cmd_result == 'Not connected.':
                print('==> wifi connection lost.')
                sleep(1)
                continue

            # get rx bitrate
            bitrate_pattern = re.compile(r'rx bitrate: (.*) MBit/s')
            rx_bitrate = bitrate_pattern.search(cmd_result).group(1)

            # get tx bitrate
            bitrate_pattern = re.compile(r'tx bitrate: (.*) MBit/s')
            tx_bitrate = bitrate_pattern.search(cmd_result).group(1)

            # get rx mcs
            rx_mcs_pattern = re.compile(r'rx.*HE-MCS ([^ ]*) ')
            rx_mcs = rx_mcs_pattern.search(cmd_result).group(1)

            # get tx mcs
            tx_mcs_pattern = re.compile(r'tx.*HE-MCS ([^ ]*) ')
            tx_mcs = tx_mcs_pattern.search(cmd_result).group(1)

            # get nss
            nss_pattern = re.compile(r'HE-NSS ([^ ]*) ')
            nss = nss_pattern.search(cmd_result).group(1)

            # get signal
            signal_pattern = re.compile(r'signal: (.*) dBm')
            signal = int(signal_pattern.search(cmd_result).group(1))

            print(f'sec: {sec}, signal: {signal} dBm. Rx_bitrate: {rx_bitrate} Mbit/s, Tx_bitrate: {tx_bitrate} Mbit/s, rx_mcs: {rx_mcs}, tx_mcs: {tx_mcs}, nss: {nss}')

            total += signal
            sleep(1)

        self.avg_signal = round(total / sec_to_test, 2)
        print(f'Avg signal: {self.avg_signal} dBm.')

    def run(self):
        print('running...')

        self.get_wifi_link_status()

        self.detect_signal(300)


if __name__ == '__main__':
    logger = Wifi_test_logger()

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
    except Exception as e:
        print(f'==> error: {e.__class__} {e}')
