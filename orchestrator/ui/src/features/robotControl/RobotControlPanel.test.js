import { fireEvent, render, screen } from '@testing-library/react';
import { RobotControls } from './RobotControlPanel';
import useRobotControl from './useRobotControl';

jest.mock('./useRobotControl');

let control;
beforeEach(() => {
  control = {
    connected: true, source: 'teleop', mode: null,
    canSetSource: true, canSetPreset: true, pending: null, notice: '', error: '',
    selected: { left: null, right: null }, setSource: jest.fn(), setPreset: jest.fn(),
  };
  useRobotControl.mockImplementation(() => control);
});

const open = () => fireEvent.click(screen.getByRole('button', { name: 'Robot controls' }));

test('keeps mode visible while controls and presets are collapsed', () => {
  render(<RobotControls robotType="robot" />);
  expect(screen.getByText('Teleop')).toBeVisible();
  expect(screen.getByText('Waiting for mode')).toBeVisible();
  expect(screen.queryByRole('button', { name: 'Use External' })).not.toBeInTheDocument();
  expect(control.setSource).not.toHaveBeenCalled();
  open();
  expect(screen.getByText('Hand presets').closest('details')).not.toHaveAttribute('open');
  expect(screen.queryByRole('button', { name: 'Use Base' })).not.toBeInTheDocument();
});

test('only explicit clicks issue source commands; current source is not an active button', () => {
  render(<RobotControls robotType="robot" />);
  open();
  expect(screen.getByRole('button', { name: 'Use Teleop' })).toBeDisabled();
  fireEvent.click(screen.getByRole('button', { name: 'Use External' }));
  expect(control.setSource).toHaveBeenCalledWith('external');
});

test('choosing preset options does not move hands until Apply is pressed', () => {
  render(<RobotControls robotType="robot" />);
  open();
  fireEvent.click(screen.getByText('Hand presets'));
  fireEvent.change(screen.getByLabelText('Left preset'), { target: { value: '2' } });
  fireEvent.change(screen.getByLabelText('Right preset'), { target: { value: '3' } });
  expect(control.setPreset).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button', { name: 'Apply hand presets' }));
  expect(control.setPreset).toHaveBeenCalledWith('both', '2', '3');
  expect(screen.getByText(/Last accepted selection in this UI/)).toHaveTextContent('Left — · Right —');
});

test('supports a custom preset ID for only one hand', () => {
  render(<RobotControls robotType="robot" />);
  open();
  fireEvent.click(screen.getByText('Hand presets'));
  fireEvent.change(screen.getByLabelText('Target hands'), { target: { value: 'right' } });
  expect(screen.queryByLabelText('Left preset')).not.toBeInTheDocument();
  fireEvent.change(screen.getByLabelText('Right preset'), { target: { value: 'custom' } });
  fireEvent.change(screen.getByLabelText('Right custom preset ID'), { target: { value: '42' } });
  fireEvent.click(screen.getByRole('button', { name: 'Apply hand presets' }));
  expect(control.setPreset).toHaveBeenCalledWith('right', '1', '42');
});

test('unsupported services provide an explanation and no preset action', () => {
  control.canSetSource = false;
  control.canSetPreset = false;
  render(<RobotControls robotType="legacy" />);
  open();
  expect(screen.getByRole('button', { name: 'Use External' })).toBeDisabled();
  expect(screen.getByText(/Source switching is unavailable/)).toBeVisible();
  expect(screen.queryByRole('button', { name: 'Apply hand presets' })).not.toBeInTheDocument();
});

test('pending requests disable all command buttons and surface failures', () => {
  control.pending = 'preset';
  control.error = 'Preset rejected';
  render(<RobotControls robotType="robot" />);
  open();
  fireEvent.click(screen.getByText('Hand presets'));
  expect(screen.getByRole('button', { name: 'Use External' })).toBeDisabled();
  expect(screen.getByRole('button', { name: 'Apply hand presets' })).toBeDisabled();
  expect(screen.getByRole('alert')).toHaveTextContent('Preset rejected');
});


test('renders Head and Base separately from the control source', () => {
  control.mode = 'head_control';
  const { rerender } = render(<RobotControls robotType="robot" />);
  expect(screen.getByText('Head')).toBeVisible();
  expect(screen.getByText('Teleop')).toBeVisible();
  control.mode = 'swerve';
  rerender(<RobotControls robotType="robot" />);
  expect(screen.getByText('Base')).toBeVisible();
  expect(screen.queryByText('Head')).not.toBeInTheDocument();
  expect(screen.getByText('Teleop')).toBeVisible();
});


test('explains a missing leader separately from waiting for a mode report', () => {
  control.modeAvailable = false;
  render(<RobotControls robotType="robot" />);
  expect(screen.getByText('Leader unavailable')).toBeVisible();
  open();
  expect(screen.getByText(/No leader mode publisher is connected/)).toBeVisible();
});
