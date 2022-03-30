#!/usr/bin/python3

import subprocess
import shlex
import sys
import os
from time import sleep
from datetime import datetime
from copy import copy
import argparse


class Ping:

    def __init__(self, ip, tos, exec_secs, interval, queue):
        super().__init__()
        self.ip = ip
        self.tos = tos
        self.exec_secs = exec_secs
        self.interval = interval
        self.q = queue

    @property
    def platform(self):
        cmd = 'uname'
        result = subprocess.check_output(
            [cmd], stderr=subprocess.STDOUT).decode('utf8').strip()
        return result

    def run(self):
        if self.platform == 'Darwin':
            tos_option_string = '-z'
            exec_secs_string = f' -t {self.exec_secs}' if self.exec_secs else ''
        elif self.platform == 'Linux':
            tos_option_string = '-Q'
            exec_secs_string = f' -c {self.exec_secs}' if self.exec_secs else ''

        interval_string = f' -i {self.interval}'

        cmd = f'ping {self.ip} {tos_option_string} {self.tos}{exec_secs_string}{interval_string}'
        print(f'==> cmd send: {cmd}\n')
        process = subprocess.Popen(shlex.split(cmd), stdout=subprocess.PIPE)

        while True:
            output = process.stdout.readline()
            if process.poll() is not None:
                break

            if output:
                line = output.strip().decode('utf8')
                try:
                    latency = float(
                        list(filter(None, line.split(' ')))[6][5:10])
                    self.q.put(latency)
                    # print(
                    #     f'{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}, dst:{self.ip}, tos: {self.tos}, latency: {latency} ms')

                except (ValueError, IndexError):
                    pass
                except Exception as e:
                    print(f'==> error: {e.__class__} {e}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', '--host', required=True,
                        type=str, help='destination ip')
    parser.add_argument('-Q', '--tos', default=0, type=int,
                        help='type of service value')
    parser.add_argument('-t', '--exec_secs', default=0, type=int,
                        help='time duration (secs)')
    parser.add_argument('-i', '--interval', default=1, type=float,
                        help='interval between packets')
    args = parser.parse_args()

    logger = Ping(args.host, args.tos, args.exec_secs, args.interval)

    print(
        f'==> start pinging : {args.host}, tos: {args.tos}, duration: {args.exec_secs} secs\n')

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