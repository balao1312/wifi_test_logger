#!/usr/bin/python3

import sys
import os
from time import sleep
from copy import copy
import argparse
import re
import pexpect


class Iperf3_runner:

    def __init__(self, host, port, tos, bitrate, reverse, udp, exec_secs, buffer_length, queue):
        super().__init__()
        self.host = host
        self.tos = tos
        self.port = port
        self.bitrate = bitrate
        self.reverse = reverse
        self.udp = udp
        self.exec_secs = exec_secs
        self.buffer_length = buffer_length
        self.q = queue

    def run(self):
        reverse_string = ' -R' if self.reverse else ''
        udp_string = ' -u' if self.udp else ''
        buffer_length_string = f' -l {self.buffer_length}' if self.buffer_length else ''

        cmd = f'iperf3 -c {self.host} -p {self.port} -S {self.tos} -b {self.bitrate} -t {self.exec_secs}{buffer_length_string}{reverse_string}{udp_string} -f m --forceflush'
        print(f'==> iperf cmd send: \n\t{cmd}\n')
        child = pexpect.spawnu(cmd, timeout=10)

        mbps_pattern = re.compile(' ([0-9.]*) Mbits\/sec')

        while True:
            try:
                child.expect('\n')
                line = child.before

                mbps = float(mbps_pattern.search(line).group(1))
                if mbps == 0.0:
                    continue
                self.q.put(mbps)

            except pexpect.exceptions.EOF:
                break
            except AttributeError:
                pass
            except Exception as e:
                print(f'==> error: {e.__class__} {e}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', '--host', required=True,
                        type=str, help='iperf server ip')
    parser.add_argument('-p', '--port', default=5201,
                        type=int, help='iperf server port')
    parser.add_argument('-S', '--tos', default=0, type=int,
                        help='type of service value')
    parser.add_argument('-b', '--bitrate', default=0,
                        type=str, help='the limit of bitrate(M/K)')
    parser.add_argument('-t', '--exec_secs', default=0, type=int,
                        help='time duration (secs)')
    parser.add_argument('-l', '--buffer_length', default=128, type=int,
                        help='length of buffer to read or write (default 128 KB for TCP, 8KB for UDP)')

    parser.add_argument('-u', '--udp', action="store_true",
                        help='use udp instead of tcp.')
    parser.add_argument('-R', '--reverse', action="store_true",
                        help='reverse to downlink from server')
    args = parser.parse_args()

    logger = Iperf3_runner(host=args.host, port=args.port, tos=args.tos,
                           bitrate=args.bitrate, reverse=args.reverse, udp=args.udp, exec_secs=args.exec_secs, buffer_length=args.buffer_length)

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
