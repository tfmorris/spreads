import logging
import os
import shutil
import tempfile

from flask import Flask
from spreads.plugin import HookPlugin, PluginOption
from spreads.vendor.pathlib import Path
from spreads.util import add_argument_from_option

app = Flask('spreadsplug.web', static_url_path='', static_folder='./client',
            template_folder='./client')
import web
import persistence
from worker import ProcessingWorker

logger = logging.getLogger('spreadsplug.web')


class WebCommands(HookPlugin):
    @classmethod
    def add_command_parser(cls, rootparser):
        cmdparser = rootparser.add_parser(
            'web', help="Start the web interface")
        cmdparser.set_defaults(subcommand=cls.run_server)
        for key, option in cls.configuration_template().iteritems():
            try:
                add_argument_from_option('web', key, option, cmdparser)
            except:
                continue

    @classmethod
    def configuration_template(cls):
        return {
            'mode': PluginOption(
                value=["full", "scanner", "processor"],
                docstring="Mode to run server in",
                selectable=True),
            'debug': PluginOption(
                value=False,
                docstring="Run server in debugging mode",
                selectable=False),
            'project_dir': PluginOption(
                value=u"~/scans",
                docstring="Directory for project folders",
                selectable=False),
            'database': PluginOption(
                value=u"~/.config/spreads/workflows.db",
                docstring="Path to application database file",
                selectable=False),
            'postprocessing_server': PluginOption(
                value=u"",  # Cannot be None because of type deduction in
                            # option parser
                docstring="Address of the postprocessing server",
                selectable=False),
        }

    @staticmethod
    def run_server(config):
        # Set rootlogger to INFO
        if config['loglevel'].get() not in ('debug', 'info'):
            for handler in logging.getLogger().handlers:
                handler.setLevel(logging.INFO)

        mode = config['web']['mode'].get()
        logger.debug("Starting scanning station server in \"{0}\" mode"
                     .format(mode))
        db_path = Path(config['web']['database'].get()).expanduser()
        project_dir = os.path.expanduser(config['web']['project_dir'].get())
        if not os.path.exists(project_dir):
            os.mkdir(project_dir)

        app.config['DEBUG'] = config['web']['debug'].get()
        app.config['mode'] = mode
        app.config['database'] = db_path
        app.config['base_path'] = project_dir
        app.config['default_config'] = config

        # Temporary directory for thumbnails, archives, etc.
        app.config['temp_dir'] = tempfile.mkdtemp()

        if mode == 'scanner':
            app.config['postproc_server'] = (
                config['web']['postprocessing_server'].get())
        if mode != 'scanner':
            worker = ProcessingWorker()
            worker.start()
        try:
            if app.config['DEBUG']:
                app.run(host="0.0.0.0", threaded=True, debug=True)
            else:
                import waitress
                waitress.serve(app, port=5000)
        finally:
            shutil.rmtree(app.config['temp_dir'])
            if mode != 'scanner':
                worker.stop()
            if app.config['DEBUG']:
                logger.info("Waiting for remaining connections to close...")