import atexit
import logging
import os
import sys


class _ErrorCountingHandler(logging.Handler):
    """Logging handler that counts records at ERROR level and above."""

    def __init__(self):
        super().__init__(level=logging.ERROR)
        self.error_count = 0

    def emit(self, record):
        self.error_count += 1


_error_handler = None


def _exit_if_errors_logged():
    # Raising SystemExit from an atexit hook does not propagate the exit code
    # in Python 3, so we have to flush manually and call os._exit. By the time
    # this runs (atexit fires in LIFO order, after main()'s normal return)
    # the script's own output is already on disk; only logging buffers remain.
    if _error_handler.error_count > 0:
        logging.shutdown()
        sys.stderr.write(f"Exiting with status 1: {_error_handler.error_count} error(s) were logged\n")
        sys.stderr.flush()
        sys.stdout.flush()
        os._exit(1)


def parse_args_and_add_logging_switch(parser):
    """Add a ``--verbosity`` switch to ``parser``, parse args, configure logging.

    Also installs a handler on the root logger that counts ERROR-level records,
    and an :mod:`atexit` hook that exits with status 1 if any were emitted, so
    that logged errors propagate as a non-zero process exit status.
    """
    global _error_handler

    parser.add_argument(
        "--verbosity",
        "-v",
        action="count",
        default=0,
        help="verbosity level: output extra non-essential info",
    )

    args = parser.parse_args()

    if args.verbosity == 0:
        logging.basicConfig(stream=sys.stderr, level=logging.WARNING)
    elif args.verbosity == 1:
        logging.basicConfig(stream=sys.stderr, level=logging.INFO)
    else:
        logging.basicConfig(stream=sys.stderr, level=logging.DEBUG)

    if _error_handler is None:
        _error_handler = _ErrorCountingHandler()
        logging.getLogger().addHandler(_error_handler)
        atexit.register(_exit_if_errors_logged)

    return args
