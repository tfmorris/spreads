import json
import os

from flask import abort, jsonify, request, send_file
from werkzeug.contrib.cache import SimpleCache

import spreads.confit as confit
from spreads.plugin import (get_pluginmanager, get_relevant_extensions,
                            get_driver)
from spreads.workflow import Workflow

from spreadsplug.web import app
import database

cache = SimpleCache()


@app.route('/')
def index():
    if app.config['mode'] == 'scanner':
        return send_file("index_scanner.html")


@app.route('/workflow', methods=['POST'])
def create_workflow():
    data = json.loads(request.data)
    path = os.path.join(app.config['base_path'], data['name'])

    # Setup default configuration
    config = confit.Configuration('spreads')
    # Overlay user-supplied values, if existant
    user_config = data.get('config', None)
    if user_config is not None:
        config.set(user_config)
    workflow = Workflow(config=config, path=path,
                        step=data.get('step', None),
                        step_done=data.get('step_done', None))
    workflow_id = database.save_workflow(workflow)
    return jsonify(id=workflow_id)


@app.route('/workflow', methods=['GET'])
def list_workflows():
    workflow_list = database.get_workflow_list()
    return jsonify(workflows=workflow_list)


@app.route('/workflow/<int:workflow_id>', methods=['GET'])
def get_workflow(workflow_id):
    workflow = database.get_workflow(workflow_id)
    if workflow is None:
        abort(404)
    out_dict = dict()
    out_dict['id'] = workflow_id
    out_dict['name'] = os.path.basename(workflow.path)
    out_dict['step'] = workflow.step
    out_dict['step_done'] = workflow.step_done
    out_dict['images'] = workflow.images
    out_dict['out_files'] = workflow.out_files
    out_dict['capture_start'] = workflow.capture_start
    return jsonify(out_dict)


@app.route('/workflow/<int:workflow_id>/config', methods=['GET'])
def get_workflow_config(workflow_id):
    workflow = database.get_workflow(workflow_id)
    if workflow is None:
        abort(404)
    return jsonify(workflow.config.flatten())


@app.route('/workflow/<int:workflow_id>/config', methods=['PUT'])
def update_workflow_config(workflow_id):
    database.update_workflow_config(workflow_id, request.data)


@app.route('/workflow/<int:workflow_id>/options', methods=['GET'])
def get_workflow_config_options(workflow_id):
    # Try to get from cache
    rv = cache.get('config-{0}'.format(workflow_id))
    if rv is not None:
        return jsonify(rv)

    workflow = database.get_workflow(workflow_id)
    pluginmanager = get_pluginmanager(workflow.config)
    scanner_extensions = ['prepare_capture', 'capture', 'finish_capture']
    processor_extensions = ['process', 'output']
    if app.config['mode'] == 'scanner':
        templates = {ext.name: ext.plugin.configuration_template()
                     for ext in get_relevant_extensions(
                         pluginmanager, scanner_extensions)}
        templates["device"] = (get_driver(workflow.config["driver"].get())
                               .driver.configuration_template())
    elif app.config['mode'] == 'processor':
        templates = {ext.name: ext.plugin.configuration_template()
                     for ext in get_relevant_extensions(
                         pluginmanager, processor_extensions)}
    elif app.config['mode'] == 'full':
        templates = {ext.name: ext.plugin.configuration_template()
                     for ext in get_relevant_extensions(
                         pluginmanager,
                         scanner_extensions + processor_extensions)}
        templates["device"] = (get_driver(workflow.config["driver"].get())
                               .driver.configuration_template())
    rv = dict()
    for plugname, options in templates.iteritems():
        if options is None:
            continue
        rv[plugname] = {key: dict(value=option.value,
                                  docstring=option.docstring,
                                  selectable=option.selectable)
                        for key, option in options.iteritems()}
    cache.set('config-{0}'.format(workflow_id), rv)
    return jsonify(rv)