"""
Goal:
  * Get monero hard fork dates from /src/hardforks/hardforks.cpp.

How to:
  * for default values and how to use the tool
    - python get_monero_hard_fork_info.py --help
  * current master:
    - python get_monero_hard_fork_info.py
    - python get_monero_hard_fork_info.py --branch master
  * It is also possible to set the branch name as environment variable: PROJECT_BRANCH_NAME.
    - PROJECT_BRANCH_NAME=master python get_monero_hard_fork_info.py
  * python get_monero_hard_fork_info.py --branch release-v0.11.0.0
        version 1 ['Apr 18 2014 UTC', '1', '1341378000']
        version 2 ['Mar 20 2016 UTC', '1009827', '1442763710']
        version 3 ['Sep 24 2016 UTC', '1141317', '1458558528']
        version 4 ['Jan 05 2017 UTC', '1220516', '1483574400']
        version 5 ['Apr 15 2017 UTC', '1288616', '1489520158']
        version 6 ['Sep 16 2017 UTC', '1400000', '1503046577']
  * python get_monero_hard_fork_info.py --branch release-v0.12
        ...
        version 7 ['Apr 06 2018 UTC', '1546000', '1521303150']
  * python get_monero_hard_fork_info.py --branch release-v0.13
        ...
        version 8 ['Oct 18 2018 UTC', '1685555', '1535889547']
        version 9 ['Oct 19 2018 UTC', '1686275', '1535889548']
        version 10 ['Mar 09 2019 UTC', '1788000', '1549792439']
        version 11 ['Mar 10 2019 UTC', '1788720', '1550225678']
  * It is possible to select the Monero network (mainnet, testnet, stagenet)
    - python get_monero_hard_fork_info.py --network stagenet
  * It is possible to select a different Monero daemon
    - python get_monero_hard_fork_info.py --daemon localhost
"""

import re
import os
import logging
import argparse
from collections import defaultdict
from datetime import datetime, timezone
import sys

import requests
from requests.exceptions import (
    ConnectionError as RequestsConnectionError,
    ReadTimeout,
    Timeout,
)


logging.basicConfig()
log = logging.getLogger(__name__)
log.setLevel(logging.INFO)

NETWORK_MODES = ["mainnet", "stagenet", "testnet"]

BRANCH_NAME = os.environ.get("PROJECT_BRANCH_NAME", None)
MONERO_NETWORK = os.environ.get("MONERO_NETWORK", None)
DAEMON_HOST = os.environ.get("DAEMON_HOST", None)

if MONERO_NETWORK and not MONERO_NETWORK in NETWORK_MODES:
    log.error(f"This is no known monero network mode {MONERO_NETWORK}")
    sys.exit(1)

TIMEOUT = 10

DAEMON_PORTS = {
    NETWORK_MODES[0]: 18081,
    NETWORK_MODES[1]: 38081,
    NETWORK_MODES[2]: 28081,
}

URL_DEFAULT = "https://raw.githubusercontent.com/monero-project/monero/{branch_name}/src/hardforks/hardforks.cpp"
URL = None
if BRANCH_NAME:
    URL = URL_DEFAULT.format(branch_name=BRANCH_NAME)
DAEMON_ADDRESS_DEFAULT = "http://{daemon_host}:{daemon_port}/json_rpc"
DAEMON_ADDRESS = None
if DAEMON_HOST and MONERO_NETWORK:
    DAEMON_ADDRESS = DAEMON_ADDRESS_DEFAULT.format(
        daemon_host=DAEMON_HOST, daemon_port=DAEMON_PORTS[MONERO_NETWORK]
    )

BEGINNING_MAINNET = "const hardfork_t mainnet_hard_forks\[\]"
BEGINNING_TESTNET = "const hardfork_t testnet_hard_forks\[\]"
BEGINNING_STAGENET = "const hardfork_t stagenet_hard_forks\[\]"
END = "};"
INFO = "{ (\d+), (\d+), (\d+), (\d+.* })"

NETWORK_RE = {
    NETWORK_MODES[0]: BEGINNING_MAINNET,
    NETWORK_MODES[1]: BEGINNING_STAGENET,
    NETWORK_MODES[2]: BEGINNING_TESTNET,
}


def get_last_and_next_hardfork(
    url=URL,
    daemon_address=DAEMON_ADDRESS,
    monero_network=MONERO_NETWORK,
    timeout=TIMEOUT,
):
    if not monero_network in NETWORK_MODES:
        log.error(f"This is no known monero network mode {monero_network}")
        sys.exit(1)

    lines = list()
    interesting = defaultdict(list)
    try:
        response = requests.get(url, timeout=timeout)

        log.debug(response.status_code)
        log.debug(response.text)
        if response.status_code != 200:
            log.error(
                f"Received HTTP status code '{response.status_code}' for '{url}' with '{response.text}'."
            )
            sys.exit(1)
        code = response.text
        start_line = re.compile(NETWORK_RE[monero_network], re.IGNORECASE)
        end_line = re.compile(END, re.IGNORECASE)
        info_line = re.compile(INFO, re.IGNORECASE)

        interesting_range = False
        lines = code.split("\n")
    except (RequestsConnectionError, ReadTimeout, Timeout) as e:
        log.error(f"Cannot get information from {host}, because: {str(e)}")

    for i, line in enumerate(lines):
        line = line.strip()
        if line:
            if start_line.match(line):
                interesting_range = True
            if end_line.match(line) and interesting_range:
                interesting_range = False
                break
            if info_line.match(line) and interesting_range:
                fork_info = list(info_line.finditer(line))
                version = fork_info[0].group(1)
                block = fork_info[0].group(2)
                difficulty = (
                    fork_info[0].group(4).translate({ord(" "): None, ord("}"): None})
                )

                data = {
                    "jsonrpc": "2.0",
                    "id": "0",
                    "method": "get_block_header_by_height",
                    "params": {"height": block},
                }
                headers = {"Content-Type": "application/json"}
                result = None
                try:
                    response = requests.post(
                        daemon_address, headers=headers, json=data, timeout=timeout
                    )
                    log.debug(response.text)
                    if response.status_code != 200:
                        log.warning(
                            f"received HTTP status code {response.status_code} with {response.text}"
                        )
                    response = response.json()
                    result = response.get("result", None)
                except (RequestsConnectionError, ReadTimeout, Timeout) as e:
                    log.error(
                        f"Cannot get info from {daemon_address}, because: {str(e)}"
                    )
                if result:
                    timestamp = result["block_header"]["timestamp"]
                    date = datetime.fromtimestamp(float(timestamp)).strftime(
                        "%b %d %Y "
                    ) + str(timezone.utc)
                else:
                    date = "---"
                # add to list
                interesting[f"Version {version}"].append(date)
                interesting[f"Version {version}"].append(block)
                interesting[f"Version {version}"].append(difficulty)

    return interesting


def main():
    parser = argparse.ArgumentParser(
        description="Get monero hard fork dates from /src/hardforks/hardforks.cpp.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "-b",
        "--branch",
        nargs="?",
        default="master",
        help="Branch to check /src/hardforks/hardforks.cpp. If not given as argument, set PROJECT_BRANCH_NAME.",
    )
    parser.add_argument(
        "-n",
        "--network",
        nargs="?",
        default=NETWORK_MODES[0],
        help="Monero network to check (mainnet, stagenet, testnet). If not given as argument, set MONERO_NETWORK.",
    )
    parser.add_argument(
        "-d",
        "--daemon",
        nargs="?",
        default="node.xmr.to",
        help="Monero dameon to use. If not given as argument, set DAEMON_HOST.",
    )
    parser.add_argument("--debug", action="store_true", help="Show debug info.")

    args = parser.parse_args()

    if args.debug:
        log.setLevel(logging.DEBUG)
    else:
        log.setLevel(logging.INFO)

    if BRANCH_NAME:
        branch_name = BRANCH_NAME
    else:
        branch_name = args.branch

    if MONERO_NETWORK:
        monero_network = MONERO_NETWORK
    else:
        monero_network = args.network
    if not monero_network in NETWORK_MODES:
        log.error(f"This is no known monero network mode {MONERO_NETWORK}")
        sys.exit(1)

    if DAEMON_HOST:
        daemon_host = DAEMON_HOST
    else:
        daemon_host = args.daemon

    url = URL_DEFAULT.format(branch_name=branch_name)
    log.info(url)

    DAEMON_ADDRESS = DAEMON_ADDRESS_DEFAULT.format(
        daemon_host=daemon_host, daemon_port=DAEMON_PORTS[monero_network]
    )
    daemon_address = f"http://{daemon_host}:{DAEMON_PORTS[monero_network]}/json_rpc"
    log.info(daemon_address)

    stuff = get_last_and_next_hardfork(
        url=url, daemon_address=daemon_address, monero_network=monero_network
    )
    for k, v in stuff.items():
        print(k, v)


if __name__ == "__main__":
    sys.exit(main())
