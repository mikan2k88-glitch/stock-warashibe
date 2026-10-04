from __future__ import annotations

import argparse
import subprocess
import sys
import time


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--attempts", type=int, default=3)
    parser.add_argument("--delay-seconds", type=int, default=20)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()

    command = list(args.command)
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        raise SystemExit("command required")
    if args.attempts < 1 or args.attempts > 3:
        raise SystemExit("attempts must be between 1 and 3")

    for attempt in range(1, args.attempts + 1):
        result = subprocess.run(command, check=False)
        if result.returncode == 0:
            if attempt > 1:
                print(f"Recovered on attempt {attempt}.")
            return 0
        if attempt == args.attempts:
            return result.returncode
        print(
            f"Attempt {attempt} failed with {result.returncode}; "
            f"retrying in {args.delay_seconds}s.",
            file=sys.stderr,
        )
        time.sleep(args.delay_seconds)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
