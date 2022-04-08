#!/usr/bin/python3

import pexpect
import subprocess
import sys
import os
from time import sleep
from copy import copy
import argparse
import re


class Ping_runner:

    def __init__(self, ip, tos, duration, interval, queue):
        super().__init__()
        self.ip = ip
        self.tos = tos
        self.duration = duration
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
            duration_string = f' -t {self.duration}' if self.duration else ''
        elif self.platform == 'Linux':
            tos_option_string = '-Q'
            duration_string = f' -c {self.duration}' if self.duration else ''

        interval_string = f' -i {self.interval}'

        cmd = f'ping {self.ip} {tos_option_string} {self.tos}{duration_string}{interval_string}'
        print(f'==> ping cmd send: \n\t{cmd}\n')

        child = pexpect.spawnu(cmd, timeout=10)
        summary_pattern = re.compile(r'rtt.*')
        latency_pattern = re.compile(r'time=([0-9.]*) ms')
        while True:
            try:
                child.expect('\n')
                line = child.before

                # get final summary and quit
                if summary_pattern.match(line):
                    return line

                latency = float(latency_pattern.search(line).group(1))
                self.q.put(latency)

            except pexpect.exceptions.EOF:
                break
            except AttributeError:
                pass
            except Exception as e:
                print(f'==> error: {e.__class__} {e}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', '--host', required=True,
                        type=str, help='destination ip')
    parser.add_argument('-Q', '--tos', default=0, type=int,
                        help='type of service value')
    parser.add_argument('-t', '--duration', default=0, type=int,
                        help='time duration (secs)')
    parser.add_argument('-i', '--interval', default=1, type=float,
                        help='interval between packets')
    args = parser.parse_args()

    logger = Ping_runner(args.host, args.tos, args.duration, args.interval)

    print(
        f'==> start pinging : {args.host}, tos: {args.tos}, duration: {args.duration} secs\n')

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
