import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { Simulate } from 'react-dom/test-utils';
import { organizationApi } from '../services/organizationApi';
import {
  AgentLocationTracker,
  ClientRegistrationPage,
  LiveLocationDashboard,
} from './OrganizationPages';

window.IS_REACT_ACT_ENVIRONMENT = true;

jest.mock('../services/organizationApi', () => ({
  organizationApi: {
    getAgentLocationTrackingStatus: jest.fn(),
    pingLocation: jest.fn(),
    registerClient: jest.fn(),
    getLiveLocations: jest.fn(),
    streamLiveLocations: jest.fn(),
    getLocationTrackingControl: jest.fn(),
    setLocationTrackingControl: jest.fn(),
    getAgentLocationTrail: jest.fn(),
  },
}));

jest.mock('react-leaflet', () => ({
  CircleMarker: () => null,
  MapContainer: () => null,
  Polyline: () => null,
  Popup: () => null,
  TileLayer: () => null,
  useMap: () => ({ fitBounds: jest.fn() }),
}));

const mountTracker = async (isFieldAgent) => {
  const container = document.createElement('div');
  document.body.appendChild(container);
  const root = createRoot(container);
  await act(async () => {
    root.render(<AgentLocationTracker isFieldAgent={isFieldAgent} />);
    await Promise.resolve();
  });
  await act(async () => { await Promise.resolve(); });
  return { container, root };
};

beforeEach(() => {
  window.sessionStorage.clear();
  organizationApi.getAgentLocationTrackingStatus.mockReset();
  organizationApi.pingLocation.mockReset().mockResolvedValue({});
  organizationApi.registerClient.mockReset().mockResolvedValue({ name: 'Test Client' });
  organizationApi.getLiveLocations.mockReset().mockResolvedValue({
    agents: [],
    refreshed_at: '2026-10-27T08:00:00',
  });
  organizationApi.streamLiveLocations.mockReset().mockImplementation(
    () => new Promise(() => {}),
  );
  organizationApi.getLocationTrackingControl.mockReset().mockRejectedValue({ status: 403 });
  organizationApi.setLocationTrackingControl.mockReset();
  organizationApi.getAgentLocationTrail.mockReset();
  Object.defineProperty(navigator, 'geolocation', {
    configurable: true,
    value: {
      getCurrentPosition: jest.fn((success) => success({
        coords: { latitude: -1.2864, longitude: 36.8172, accuracy: 12 },
      })),
    },
  });

});

test('automatically sends a location when the system schedule is active', async () => {
  organizationApi.getAgentLocationTrackingStatus.mockResolvedValue({ enabled: true });
  const { container, root } = await mountTracker(true);

  expect(organizationApi.getAgentLocationTrackingStatus).toHaveBeenCalledTimes(1);
  expect(organizationApi.pingLocation).toHaveBeenCalledWith({
    latitude: -1.2864,
    longitude: 36.8172,
    accuracy_meters: 12,
  }, expect.any(AbortSignal));
  expect(window.sessionStorage.getItem('okoa_location_tracking')).toBe('enabled');

  await act(async () => root.unmount());
  container.remove();
});

test('does not request or send locations for non-field agents', async () => {
  const { container, root } = await mountTracker(false);

  expect(organizationApi.getAgentLocationTrackingStatus).not.toHaveBeenCalled();
  expect(organizationApi.pingLocation).not.toHaveBeenCalled();

  await act(async () => root.unmount());
  container.remove();
});

test('does not request GPS outside the system schedule', async () => {
  organizationApi.getAgentLocationTrackingStatus.mockResolvedValue({ enabled: false });
  const { container, root } = await mountTracker(true);

  expect(organizationApi.getAgentLocationTrackingStatus).toHaveBeenCalledTimes(1);
  expect(navigator.geolocation.getCurrentPosition).not.toHaveBeenCalled();
  expect(organizationApi.pingLocation).not.toHaveBeenCalled();

  await act(async () => root.unmount());
  container.remove();
});

test('refreshes live positions if the authenticated stream stops sending updates', async () => {
  jest.useFakeTimers();
  organizationApi.getLiveLocations.mockResolvedValue({
    agents: [],
    refreshed_at: '2026-10-27T08:00:00',
  });
  const container = document.createElement('div');
  document.body.appendChild(container);
  const root = createRoot(container);

  await act(async () => {
    root.render(<LiveLocationDashboard />);
    await Promise.resolve();
    await Promise.resolve();
  });
  expect(organizationApi.getLiveLocations).toHaveBeenCalledTimes(1);

  await act(async () => {
    jest.advanceTimersByTime(30000);
    await Promise.resolve();
    await Promise.resolve();
  });
  expect(organizationApi.getLiveLocations).toHaveBeenCalledTimes(2);

  await act(async () => root.unmount());
  container.remove();
  jest.useRealTimers();
});

test('marks agent-opted active visits on the supervisor location view', async () => {
  organizationApi.getLiveLocations.mockResolvedValue({
    agents: [{
      user_id: 21,
      name: 'Field Agent',
      department: 'Sales & Marketing',
      active_visit: true,
      sharing_status: 'on',
      is_live: true,
      latitude: -1.2864,
      longitude: 36.8172,
      recorded_at: new Date().toISOString(),
      trail: [],
    }],
    refreshed_at: new Date().toISOString(),
  });
  const container = document.createElement('div');
  document.body.appendChild(container);
  const root = createRoot(container);

  await act(async () => {
    root.render(<LiveLocationDashboard />);
    await Promise.resolve();
    await Promise.resolve();
  });

  expect(container.textContent).toContain('Active field visit · sharing now');
  expect(organizationApi.getLiveLocations).toHaveBeenCalledTimes(1);

  await act(async () => root.unmount());
  container.remove();
});

test('loads all scoped agent trails and provides forward and reverse map playback', async () => {
  const firstPointTime = new Date(Date.now() - 60 * 60 * 1000).toISOString();
  const secondPointTime = new Date(Date.now() - 30 * 60 * 1000).toISOString();
  organizationApi.getLiveLocations.mockResolvedValue({
    agents: [
      { user_id: 11, name: 'Agent One', department: 'Sales & Marketing', trail: [] },
      { user_id: 12, name: 'Agent Two', department: 'Sales & Marketing', trail: [] },
    ],
    refreshed_at: new Date().toISOString(),
  });
  organizationApi.getAgentLocationTrail.mockImplementation((userId) => Promise.resolve({
    trail: [
      {
        latitude: -1.2864 + userId / 1000,
        longitude: 36.8172,
        recorded_at: firstPointTime,
        is_simulated: false,
      },
      {
        latitude: -1.2864 + userId / 500,
        longitude: 36.8272,
        recorded_at: secondPointTime,
        is_simulated: false,
      },
    ],
  }));
  const container = document.createElement('div');
  document.body.appendChild(container);
  const root = createRoot(container);

  await act(async () => {
    root.render(<LiveLocationDashboard />);
    await Promise.resolve();
    await Promise.resolve();
  });
  await act(async () => {
    [...container.querySelectorAll('button')]
      .find((button) => button.textContent === 'Load all agent locations')
      .click();
    await Promise.resolve();
    await Promise.resolve();
  });
  await act(async () => {
    Simulate.change(container.querySelector('#all-agent-location-scrubber'), {
      target: { value: String(Date.now() - 15 * 60 * 1000) },
    });
  });

  expect(organizationApi.getAgentLocationTrail).toHaveBeenCalledTimes(2);
  expect(container.textContent).toContain('2 of 2 agents have a location at this time');
  const reverseButton = [...container.querySelectorAll('button')]
    .find((button) => button.textContent === 'Play reverse');
  const forwardButton = [...container.querySelectorAll('button')]
    .find((button) => button.textContent === 'Play forward');
  expect(reverseButton).toBeTruthy();
  expect(forwardButton).toBeTruthy();

  await act(async () => reverseButton.click());
  expect(reverseButton.getAttribute('aria-pressed')).toBe('true');
  await act(async () => forwardButton.click());
  expect(forwardButton.getAttribute('aria-pressed')).toBe('true');

  await act(async () => root.unmount());
  container.remove();
});

test('client registration route uses the sequential sales report workflow', async () => {
  const container = document.createElement('div');
  document.body.appendChild(container);
  const root = createRoot(container);
  await act(async () => {
    root.render(<ClientRegistrationPage />);
  });

  expect(container.textContent).toContain('Sales report');
  expect([...container.querySelectorAll('button')].some((button) => button.textContent === 'Add New Client')).toBe(true);

  await act(async () => Simulate.click([...container.querySelectorAll('button')].find((button) => button.textContent === 'Add New Client')));
  await act(async () => Simulate.click([...container.querySelectorAll('.sales-choice-buttons button')].find((button) => button.textContent === 'Existing Client')));
  await act(async () => Simulate.click([...container.querySelectorAll('.sales-choice-buttons button')].find((button) => button.textContent === 'YES')));

  expect(container.textContent).toContain('Daily client report');
  expect(container.textContent).toContain('Existing client interaction');
  expect(container.textContent).toContain('Referral Name');
  expect(container.querySelector('input[name="name"]')).toBeNull();
  expect(organizationApi.registerClient).not.toHaveBeenCalled();

  await act(async () => root.unmount());
  container.remove();
});
