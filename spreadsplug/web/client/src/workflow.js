/* global require */
(function() {
  'use strict';

  var Backbone = require('backbone'),
      _ = require('underscore'),
      jQuery = require('jquery')(window),
      Workflow;
  // Custom third party extension to Backbone, see below
  Backbone.DeepModel = require('../lib/backbone-deep-model.js');
  // Load Backbone.Validation extension
  require('backbone-validation');
  _.extend(Backbone.DeepModel.prototype, Backbone.Validation.mixin);

  /* We extend DeepModel instead of Model so we can listen on changes for
   * nested objects like workflow.config. */
  Workflow = Backbone.DeepModel.extend({
    // Don't synchronize these with the server
    blacklist: ['configuration_template'],
    toJSON: function(options) {
        return _.omit(this.attributes, this.blacklist);
    },
    initialize: function() {
      this._setConfigurationTemplate();
      this._setPluginValidators();
      if (this.isNew()) {
        this._setDefaultConfiguration();
        this.on('sync', this._startPolling, this);
      } else {
        this._startPolling();
      }
      this.on('destroy', function() {
        this._keepPolling = false;
      });
    },
    validation: {
      name: {
        required: true,
        // All printable ASCII characters, except '/'
        pattern: /^[\x20-\x2E\x30-\x7E]*$/,
        msg: 'Non-ASCII characters and "/" are not permitted.'
      }
    },
    validate: function() {
      // NOTE: We monkey patch the stupid Backbone.Validation mixin, as it
      // pretends as if validation is always successful...
      return Backbone.Validation.mixin.validate.bind(this)();
    },
    submit: function() {
      console.debug("Submitting workflow " + this.id + " for postprocessing");
      jQuery.post('/workflow/' + this.id + '/submit')
        .fail(function() {
          console.error("Could not submit workflow " + this.id);
        });
    },
    queue: function() {
      jQuery.post('/queue', {id: this.id}, function(data, status) {
        this.queueId = data.queue_position;
      });
    },
    dequeue: function() {
      jQuery.ajax({
        type: "DELETE",
        url: '/queue/' + this.queueId,
      }).fail(function() {
        console.error("Could not delete workflow " + this.id + " from queue");
      });
    },
    triggerCapture: function(retake) {
      jQuery.post(
        '/workflow/' + this.id + "/capture" + (retake ? '?retake=true' : ''),
        function(data, status) {
          console.debug("Capture succeeded");
          this.set('images', data.images);
        }.bind(this)).fail(function() {
          console.error("Capture failed");
        });
    },
    finishCapture: function() {
      jQuery.post('/workflow/' + this.id + "/capture/finish", function() {
        console.debug("Capture successfully finished");
      }).fail(function() {
        console.error("Capture could not be finished.");
      });
    },
    _setConfigurationTemplate: function() {
      jQuery.ajax({
        type: "GET",
        url: '/plugins',
        success: function(data) {
          var template;
          // Filter out emptyjj
          template = _.omit(data, _.filter(_.keys(data), function(key){
            return _.isEmpty(data[key]);
          }));
          this.set('configuration_template', template);
        }.bind(this),
        async: false
      }).fail(function() {
        console.error("Could not obtain configuration");
      });
    },
    _setDefaultConfiguration: function() {
      var templates = this.get('configuration_template');
      _.each(templates, function(template, plugin) {
        _.each(template, function(option, name) {
          var path = 'config.' + plugin + '.' + name;
          if (option.selectable) {
            this.set(path, option.value[0]);
          } else {
            this.set(path, option.value);
          }
        }, this);
      }, this);
    },
    _setPluginValidators: function() {
      var templates = this.get('configuration_template');
      _.each(templates, function(template, plugin) {
        _.each(template, function(option, name) {
          var path = 'config.' + plugin + '.' + name;
          if (option.selectable) {
            this.validation[path] = {
              oneOf: option.value
            };
          } else if (_.isNumber(option.value)) {
            this.validation[path] = {
              pattern: 'number',
              msg: 'Must be a number.'
            };
          }
        }, this);
      }, this);
    },
    _startPolling: function() {
      if (!this._keepPolling) {
        this._keepPolling = true;
      } else {
        return;
      }
      (function poll() {
        if (!this._keepPolling) return;
        $.ajax({
            url: "/workflow/" + this.id + "/poll",
            success: function(data){
                this.set(data);
            }.bind(this),
            dataType: "json",
            complete: function(xhr, status) {
                if (_.contains(["timeout", "success"], status)) poll.bind(this)();
                else _.delay(poll.bind(this), 30*1000);
            }.bind(this),
            timeout: 2*60*1000
        });
      }.bind(this)());
    }
  });

  module.exports = Backbone.Collection.extend({
    model: Workflow,
    url: '/workflow'
  });
}());