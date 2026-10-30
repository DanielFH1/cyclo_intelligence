// Copyright 2026 ROBOTIS CO., LTD.
// Licensed under the Apache License, Version 2.0.

import { useEffect, useRef, useState } from 'react';
import { useSelector } from 'react-redux';
import ROSLIB from 'roslib';
import rosConnectionManager from '../../utils/rosConnectionManager';
import {
  DEFAULT_MODE_TOPIC, PRESET_SERVICE, PRESET_TYPE, SOURCE_SERVICE,
  SOURCE_STALE_MS, SOURCE_TOPIC, SOURCE_TYPE, normalizeSource, presetRequest,
} from './controlProtocol';

const emptyState = () => ({
  connected: false, source: null, mode: null, modeAvailable: null,
  canSetSource: false, canSetPreset: false,
  pending: null, notice: '', error: '', selected: { left: null, right: null },
});

// Commands are never queued for a later connection or retried automatically.
function callService(ros, name, serviceType, args, timeout = 4000) {
  return new Promise((resolve, reject) => {
    if (!ros.isConnected) { reject(new Error('Robot connection lost.')); return; }
    const id = `call_service:${name}:${++ros.idCounter}`;
    let done = false;
    const finish = (callback, value) => {
      if (done) return;
      done = true;
      clearTimeout(timer);
      ros.off(id, onResponse);
      ros.off('close', onClose);
      callback(value);
    };
    const onResponse = (message) => {
      if (message.result === false) {
        finish(reject, new Error(message.values?.message || String(message.values)));
      } else {
        finish(resolve, message.values || {});
      }
    };
    const onClose = () => finish(reject, new Error(
      'Robot connection lost. The outcome is unknown; check the robot before retrying.'
    ));
    const timer = setTimeout(() => finish(reject, new Error(
      'No service response. The outcome is unknown; check the robot before retrying.'
    )), timeout);
    ros.on(id, onResponse);
    ros.on('close', onClose);
    try {
      // Own the response listener so unanswered discovery/command requests
      // cannot accumulate listeners on a long-lived ROS connection.
      ros.callOnConnection({
        op: 'call_service', id, service: name, type: serviceType,
        args, timeout: timeout / 1000,
      });
    } catch (error) { finish(reject, error); }
  });
}

export default function useRobotControl(robotType, modeTopic = DEFAULT_MODE_TOPIC) {
  const url = useSelector((state) => state.ros.rosbridgeUrl);
  const [state, setState] = useState(emptyState);
  const session = useRef(null);

  useEffect(() => {
    let current = null;
    let stopped = false;
    const patch = (ctx, values) => {
      if (!stopped && current === ctx) setState((old) => ({ ...old, ...values }));
    };
    const detach = () => {
      if (current) {
        current.alive = false;
        current.subscriptions.forEach((topic) => topic.unsubscribe());
        current.ros.off('close', current.onClose);
        current.ros.off('error', current.onClose);
      }
      current = null;
      session.current = null;
      if (!stopped) setState(emptyState());
    };
    const discover = async (ctx) => {
      if (ctx.discovering) return;
      ctx.discovering = true;
      ctx.discoveryAt = Date.now();
      try {
        const [source, presets, mode] = await Promise.all([
          callService(ctx.ros, '/rosapi/services_for_type', 'rosapi_msgs/srv/ServicesForType', { type: SOURCE_TYPE }),
          callService(ctx.ros, '/rosapi/services_for_type', 'rosapi_msgs/srv/ServicesForType', { type: PRESET_TYPE }),
          modeTopic ? callService(ctx.ros, '/rosapi/publishers', 'rosapi_msgs/srv/Publishers', { topic: modeTopic }) : Promise.resolve({ publishers: [] }),
        ]);
        if (!ctx.alive) return;
        ctx.canSetSource = source.services?.includes(SOURCE_SERVICE) === true;
        ctx.canSetPreset = presets.services?.includes(PRESET_SERVICE) === true;
        patch(ctx, {
          canSetSource: ctx.canSetSource, canSetPreset: ctx.canSetPreset,
          modeAvailable: Array.isArray(mode.publishers) && mode.publishers.length > 0,
          ...(!mode.publishers?.length ? { mode: null } : {}),
          ...(!ctx.canSetPreset ? { selected: { left: null, right: null } } : {}),
        });
      } catch (_) {
        ctx.canSetSource = false;
        ctx.canSetPreset = false;
        patch(ctx, { canSetSource: false, canSetPreset: false, mode: null, modeAvailable: null, selected: { left: null, right: null } });
      } finally { ctx.discovering = false; }
    };
    const tick = () => {
      const ros = robotType && url ? rosConnectionManager.getCurrentConnection() : null;
      if (!ros || !ros.isConnected) {
        if (current) detach();
        return;
      }
      if (current?.ros !== ros) {
        detach();
        const ctx = {
          ros, alive: true, subscriptions: [], source: null, sourceAt: 0, sourceSequence: 0,
          busy: false, canSetSource: false, canSetPreset: false, discoveryAt: 0,
        };
        current = ctx;
        session.current = ctx;
        ctx.patch = (values) => patch(ctx, values);
        ctx.onClose = () => { if (current === ctx) detach(); };
        ros.on('close', ctx.onClose);
        ros.on('error', ctx.onClose);
        patch(ctx, { connected: true });
        const subscribe = (name, callback) => {
          const topic = new ROSLIB.Topic({
            ros, name, messageType: 'std_msgs/msg/String', queue_length: 1,
            reconnect_on_close: false,
          });
          // roslib 1.x assigns this method unbound when reconnect_on_close is
          // false. Bind it explicitly; this hook owns subscription lifetimes.
          topic.callForSubscribeAndAdvertise = ros.callOnConnection.bind(ros);
          topic.subscribe((message) => { if (ctx.alive) callback(message); });
          ctx.subscriptions.push(topic);
        };
        subscribe(SOURCE_TOPIC, (message) => {
          ctx.source = normalizeSource(message.data);
          ctx.sourceAt = Date.now();
          ctx.sourceSequence += 1;
          patch(ctx, { source: ctx.source });
        });
        if (modeTopic) subscribe(modeTopic, (message) => {
          patch(ctx, { mode: typeof message.data === 'string' ? message.data : null, modeAvailable: true });
        });
      }
      const ctx = current;
      if (ctx.source && Date.now() - ctx.sourceAt > SOURCE_STALE_MS) {
        ctx.source = null;
        patch(ctx, { source: null, mode: null });
      }
      if (!ctx.discoveryAt || Date.now() - ctx.discoveryAt >= 5000) discover(ctx);
    };
    tick();
    const timer = setInterval(tick, 500);
    return () => { stopped = true; clearInterval(timer); detach(); };
  }, [robotType, url, modeTopic]);

  const run = async (kind, action) => {
    const ctx = session.current;
    if (!ctx?.alive || !ctx.ros.isConnected || ctx.busy) return;
    ctx.busy = true;
    ctx.patch({ pending: kind, notice: '', error: '' });
    try { await action(ctx); }
    catch (error) { if (ctx.alive) ctx.patch({ error: error.message }); }
    finally {
      ctx.busy = false;
      if (ctx.alive) ctx.patch({ pending: null });
    }
  };

  const setSource = (source) => run('source', async (ctx) => {
    if (!['external', 'teleop'].includes(source) || !ctx.canSetSource ||
        !ctx.source || Date.now() - ctx.sourceAt > SOURCE_STALE_MS) {
      throw new Error('Source control is unavailable. Wait for live robot status.');
    }
    const sequence = ctx.sourceSequence;
    const response = await callService(ctx.ros, SOURCE_SERVICE, SOURCE_TYPE, { data: source === 'teleop' });
    if (!ctx.alive) return;
    if (response.success !== true) throw new Error(response.message || 'Source change rejected.');
    ctx.patch({ notice: 'Request accepted. Waiting for the robot to report the source…' });
    const deadline = Date.now() + 6000;
    while (ctx.alive && Date.now() < deadline) {
      if (ctx.sourceSequence > sequence && ctx.source === source && Date.now() - ctx.sourceAt <= SOURCE_STALE_MS) {
        ctx.patch({ notice: `Source confirmed: ${source === 'teleop' ? 'Teleop' : 'External'}.` });
        return;
      }
      await new Promise((resolve) => setTimeout(resolve, 100));
    }
    if (ctx.alive) throw new Error('Source request was accepted, but completion was not confirmed. Check the live source before retrying.');
  });

  const setPreset = (target, left, right) => run('preset', async (ctx) => {
    if (!ctx.canSetPreset) throw new Error('Hand preset control is unavailable on this robot.');
    const request = presetRequest(target, left, right);
    const response = await callService(ctx.ros, PRESET_SERVICE, PRESET_TYPE, request);
    if (!ctx.alive) return;
    if (response.accepted !== true) throw new Error(response.message || 'Preset selection rejected.');
    setState((old) => ({
      ...old,
      selected: {
        left: target === 'right' ? old.selected.left : request.left_preset_id,
        right: target === 'left' ? old.selected.right : request.right_preset_id,
      },
      notice: response.message || 'Hand preset selection accepted.',
    }));
  });

  return { ...state, setSource, setPreset };
}
