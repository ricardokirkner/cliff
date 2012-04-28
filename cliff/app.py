"""Application base class.
"""

import argparse
import logging
import logging.handlers
import os
import sys

from .help import HelpAction, HelpCommand
from .interactive import InteractiveApp

LOG = logging.getLogger(__name__)


class App(object):
    """Application base class.
    """

    NAME = os.path.splitext(os.path.basename(sys.argv[0]))[0]

    CONSOLE_MESSAGE_FORMAT = '%(message)s'
    LOG_FILE_MESSAGE_FORMAT = '[%(asctime)s] %(levelname)-8s %(name)s %(message)s'
    DEFAULT_VERBOSE_LEVEL = 1

    def __init__(self, description, version, command_manager,
                 stdin=None, stdout=None, stderr=None):
        """Initialize the application.

        :param description: One liner explaining the program purpose
        :param version: String containing the application version number
        :param command_manager: A CommandManager instance
        :param stdin: Standard input stream
        :param stdout: Standard output stream
        :param stderr: Standard error output stream
        """
        self.command_manager = command_manager
        self.command_manager.add_command('help', HelpCommand)
        self.stdin = stdin or sys.stdin
        self.stdout = stdout or sys.stdout
        self.stderr = stderr or sys.stderr
        self.parser = self.build_option_parser(description, version)
        self.interactive_mode = False

    def build_option_parser(self, description, version):
        """Return an argparse option parser for this application.

        Subclasses may override this method to extend
        the parser with more global options.
        """
        parser = argparse.ArgumentParser(
            description=description,
            add_help=False,
            )
        parser.add_argument(
            '--version',
            action='version',
            version='%(prog)s {}'.format(version),
            )
        parser.add_argument(
            '-v', '--verbose',
            action='count',
            dest='verbose_level',
            default=self.DEFAULT_VERBOSE_LEVEL,
            help='Increase verbosity of output. Can be repeated.',
            )
        parser.add_argument(
            '-q', '--quiet',
            action='store_const',
            dest='verbose_level',
            const=0,
            help='suppress output except warnings and errors',
            )
        parser.add_argument(
            '-h', '--help',
            action=HelpAction,
            nargs=0,
            default=self.command_manager,  # tricky
            help="show this help message and exit",
            )
        parser.add_argument(
            '--debug',
            default=False,
            action='store_true',
            help='show tracebacks on errors',
            )
        return parser

    def configure_logging(self):
        """Create logging handlers for any log output.
        """
        root_logger = logging.getLogger('')

        # Set up logging to a file
        root_logger.setLevel(logging.DEBUG)
        file_handler = logging.handlers.RotatingFileHandler(
            self.NAME + '.log',
            maxBytes=10240,
            backupCount=1,
            )
        formatter = logging.Formatter(self.LOG_FILE_MESSAGE_FORMAT)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

        # Send higher-level messages to the console via stderr
        console = logging.StreamHandler()
        console_level = {0: logging.WARNING,
                         1: logging.INFO,
                         2: logging.DEBUG,
                         }.get(self.options.verbose_level, logging.DEBUG)
        console.setLevel(console_level)
        formatter = logging.Formatter(self.CONSOLE_MESSAGE_FORMAT)
        console.setFormatter(formatter)
        root_logger.addHandler(console)
        return

    def run(self, argv):
        """Equivalent to the main program for the application.
        """
        self.options, remainder = self.parser.parse_known_args(argv)
        self.configure_logging()
        self.initialize_app()
        result = 1
        if not remainder:
            result = self.interact()
        else:
            result = self.run_subcommand(remainder)
        return result

    # FIXME(dhellmann): Consider moving these command handling methods
    # to a separate class.
    def initialize_app(self):
        """Hook for subclasses to take global initialization action
        after the arguments are parsed but before a command is run.
        Invoked only once, even in interactive mode.
        """
        return

    def prepare_to_run_command(self, cmd):
        """Perform any preliminary work needed to run a command.
        """
        return

    def clean_up(self, cmd, result, err):
        """Hook run after a command is done to shutdown the app.
        """
        return

    def interact(self):
        self.interactive_mode = True
        interpreter = InteractiveApp(self, self.command_manager, self.stdin, self.stdout)
        interpreter.prompt = '(%s) ' % self.NAME
        interpreter.cmdloop()
        return 0

    def run_subcommand(self, argv):
        cmd_factory, cmd_name, sub_argv = self.command_manager.find_command(argv)
        cmd = cmd_factory(self, self.options)
        err = None
        result = 1
        try:
            self.prepare_to_run_command(cmd)
            full_name = cmd_name if self.interactive_mode else ' '.join([self.NAME, cmd_name])
            cmd_parser = cmd.get_parser(full_name)
            parsed_args = cmd_parser.parse_args(sub_argv)
            result = cmd.run(parsed_args)
        except Exception as err:
            if self.options.debug:
                LOG.exception(err)
                raise
            LOG.error('ERROR: %s', err)
        finally:
            try:
                self.clean_up(cmd, result, err)
            except Exception as err2:
                if self.options.debug:
                    LOG.exception(err2)
                else:
                    LOG.error('Could not clean up: %s', err2)
        return result
