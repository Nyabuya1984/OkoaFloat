import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { organizationApi } from '../services/organizationApi';
import ActiveFieldVisitLocation from './ActiveFieldVisitLocation';

window.IS_REACT_ACT_ENVIRONMENT = true;

jest.mock('../services/organizationApi', () => ({
  organizationApi: {
    pingLocation: jest.fn(),
    setActiveFieldVisit: jest.fn(),
  },
}));

const mount = async (props = { enabled: true }) => {
  const container = document.createElement('div');
  document.body.appendChild(container);
  const root = createRoot(container);
  await act(async () => root.render(<ActiveFieldVisitLocation {...props} />));
  return { container, root };
};

beforeEach(() => {
  organizationApi.pingLocation.mockReset().mockResolvedValue({});
  organizationApi.setActiveFieldVisit.mockReset().mockResolvedValue({});
  Object.defineProperty(navigator, 'geolocation', {
    configurable: true,
    value: {
      getCurrentPosition: jest.fn((success) => success({
        coords: { latitude: -1.2864, longitude: 36.8172, accuracy: 12 },
      })),
    },
  });
});

test('does not request location until the agent explicitly opts in', async () => {
  const { container, root } = await mount();

  expect(navigator.geolocation.getCurrentPosition).not.toHaveBeenCalled();
  expect(organizationApi.setActiveFieldVisit).not.toHaveBeenCalled();
  expect(container.textContent).toContain('Location sharing is OFF');

  await act(async () => {
    container.querySelector('button').click();
    await Promise.resolve();
    await Promise.resolve();
  });

  expect(navigator.geolocation.getCurrentPosition).toHaveBeenCalledTimes(1);
  expect(organizationApi.setActiveFieldVisit).toHaveBeenCalledWith('start');
  expect(organizationApi.pingLocation).toHaveBeenCalledWith({
    latitude: -1.2864,
    longitude: 36.8172,
    accuracy_meters: 12,
  }, undefined, 'active_visit');
  expect(container.textContent).toContain('Location sharing is ON');

  await act(async () => {
    [...container.querySelectorAll('button')]
      .find((button) => button.textContent.includes('End visit'))
      .click();
    await Promise.resolve();
  });
  expect(organizationApi.setActiveFieldVisit).toHaveBeenLastCalledWith('stop', { keepalive: false });
  expect(container.textContent).toContain('Location sharing is OFF');

  await act(async () => root.unmount());
  container.remove();
});

test('stops sharing when the field visit ends or the page session unmounts', async () => {
  const { container, root } = await mount({ enabled: true, endSignal: 0 });
  await act(async () => {
    container.querySelector('button').click();
    await Promise.resolve();
    await Promise.resolve();
  });

  await act(async () => root.render(<ActiveFieldVisitLocation enabled endSignal={1} />));
  expect(organizationApi.setActiveFieldVisit).toHaveBeenLastCalledWith('stop', { keepalive: false });

  await act(async () => {
    container.querySelector('button').click();
    await Promise.resolve();
    await Promise.resolve();
  });
  await act(async () => root.unmount());
  expect(organizationApi.setActiveFieldVisit).toHaveBeenLastCalledWith('stop', { keepalive: true });
  container.remove();
});

test('does not request GPS or start server sharing when disabled', async () => {
  const { container, root } = await mount({ enabled: false });
  expect(navigator.geolocation.getCurrentPosition).not.toHaveBeenCalled();
  expect(organizationApi.setActiveFieldVisit).not.toHaveBeenCalled();
  expect(container.textContent).toBe('');
  await act(async () => root.unmount());
  container.remove();
});

test('permission denial does not start a server-side visit', async () => {
  navigator.geolocation.getCurrentPosition.mockImplementation((success, fail) => {
    fail({ code: 1, PERMISSION_DENIED: 1 });
  });
  const { container, root } = await mount();

  await act(async () => {
    container.querySelector('button').click();
    await Promise.resolve();
  });

  expect(organizationApi.setActiveFieldVisit).not.toHaveBeenCalled();
  expect(organizationApi.pingLocation).not.toHaveBeenCalled();
  expect(container.textContent).toContain('Location permission was denied');
  await act(async () => root.unmount());
  container.remove();
});
