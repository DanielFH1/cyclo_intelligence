// Copyright 2026 ROBOTIS CO., LTD.
// Licensed under the Apache License, Version 2.0.

import React, { useState } from 'react';
import { useSelector } from 'react-redux';
import { MdGamepad, MdExpandLess, MdExpandMore } from 'react-icons/md';
import useRobotControl from './useRobotControl';
import { DEFAULT_MODE_TOPIC, modeLabel } from './controlProtocol';
import './RobotControlPanel.css';

export default function RobotControlPanel() {
  const robotType = useSelector((state) => state.tasks.robotType);
  // A new robot selection must not retain the previous robot's input drafts.
  return robotType ? <RobotControls key={robotType} robotType={robotType} /> : null;
}

export function RobotControls({ robotType, modeTopic = DEFAULT_MODE_TOPIC }) {
  const control = useRobotControl(robotType, modeTopic);
  const [expanded, setExpanded] = useState(false);
  const [target, setTarget] = useState('both');
  const [left, setLeft] = useState('1');
  const [right, setRight] = useState('1');
  const sourceLabel = control.source === 'teleop' ? 'Teleop' : control.source === 'external' ? 'External' : 'Unknown';
  const joystickLabel = control.mode ? modeLabel(control.mode)
    : control.modeAvailable === false ? 'Leader unavailable' : 'Waiting for mode';
  const disabled = !control.connected || Boolean(control.pending);

  return (
    <section className="robot-control" aria-label="Robot controls">
      <div className="robot-control-summary">
        <button type="button" className="robot-control-toggle" aria-expanded={expanded}
          aria-controls="robot-control-details" onClick={() => setExpanded((value) => !value)}>
          <MdGamepad aria-hidden="true" /> Robot controls
          {expanded ? <MdExpandLess aria-hidden="true" /> : <MdExpandMore aria-hidden="true" />}
        </button>
        <span className={`robot-control-badge ${control.source ? `is-${control.source}` : ''}`}>
          Source: <strong>{sourceLabel}</strong>
        </span>
        <span className="robot-control-badge" title="Last mode reported by the leader; reset after reconnecting.">
          Joystick: <strong>{joystickLabel}</strong>{control.mode ? ' · last reported' : ''}
        </span>
        {!control.connected && <span className="robot-control-muted">Disconnected</span>}
        {control.pending && <span role="status">Request in progress…</span>}
      </div>
      {expanded && (
        <div id="robot-control-details" className="robot-control-details">
          <div className="robot-control-section">
            <h2>Control source</h2>
            <div className="robot-control-actions">
              {['external', 'teleop'].map((source) => (
                <button key={source} type="button" aria-pressed={control.source === source}
                  disabled={disabled || !control.canSetSource || !control.source || control.source === source}
                  onClick={() => control.setSource(source)}>
                  {source === 'teleop' ? 'Use Teleop' : 'Use External'}
                </button>
              ))}
            </div>
            <p>Teleop uses the leader. External uses model or external commands. Switching source can clear arm activation; enable the desired arms with the leader afterward.</p>
            {!control.canSetSource && <p className="robot-control-muted">Source switching is unavailable on this robot.</p>}
            {control.canSetSource && !control.source && <p className="robot-control-muted">Waiting for live source status.</p>}
          </div>
          <div className="robot-control-section">
            <h2>Joystick mode · {joystickLabel}</h2>
            <p>To switch Head / Base, briefly press and release both leader buttons together (less than 0.5 s).</p>
            <p className="robot-control-muted">{control.modeAvailable === false
              ? 'No leader mode publisher is connected. Start the leader to receive Head / Base updates.'
              : 'The mode updates when the leader reports a change. Briefly press and release both buttons to report the selected mode.'}</p>
          </div>
          <details className="robot-control-presets">
            <summary>Hand presets {control.canSetPreset ? '' : '· unavailable'}</summary>
            {control.canSetPreset ? (
              <div className="robot-control-preset-body">
                <p>Selecting a preset can move enabled hands. Names below describe the default AI Worker presets; use the configured ID for custom presets.</p>
                <form onSubmit={(event) => { event.preventDefault(); control.setPreset(target, left, right); }}>
                  <div className="robot-control-actions">
                    <label>Target hands
                      <select value={target} onChange={(event) => setTarget(event.target.value)} disabled={disabled}>
                        <option value="both">Both hands</option><option value="left">Left hand</option><option value="right">Right hand</option>
                      </select>
                    </label>
                    {target !== 'right' && <PresetInput side="Left" value={left} onChange={setLeft} disabled={disabled} />}
                    {target !== 'left' && <PresetInput side="Right" value={right} onChange={setRight} disabled={disabled} />}
                    <button type="submit" disabled={disabled}>Apply hand presets</button>
                  </div>
                </form>
                <p>Last accepted selection in this UI: Left {control.selected.left ?? '—'} · Right {control.selected.right ?? '—'}</p>
                <p className="robot-control-muted">The controller does not report its current hand preset or motion completion. Changes made elsewhere are not reflected here.</p>
              </div>
            ) : <p className="robot-control-muted">Connect a robot with hand preset support to use this control.</p>}
          </details>
        </div>
      )}
      {control.notice && <p className="robot-control-feedback" role="status">{control.notice}</p>}
      {control.error && <p className="robot-control-feedback robot-control-error" role="alert">{control.error}</p>}
    </section>
  );
}

function PresetInput({ side, value, onChange, disabled }) {
  const standard = ['1', '2', '3'].includes(value);
  const [custom, setCustom] = useState(!standard);
  return (
    <label>{side} preset
      <select aria-label={`${side} preset`} value={custom ? 'custom' : value} disabled={disabled}
        onChange={(event) => {
          setCustom(event.target.value === 'custom');
          if (event.target.value !== 'custom') onChange(event.target.value);
        }}>
        <option value="1">1 · Envelope</option><option value="2">2 · Pinch</option><option value="3">3 · Three-finger</option>
        <option value="custom">Custom ID</option>
      </select>
      {custom && <input aria-label={`${side} custom preset ID`} type="number" min="1" max="65535" step="1"
        required value={value} disabled={disabled} onChange={(event) => onChange(event.target.value)} />}
    </label>
  );
}
