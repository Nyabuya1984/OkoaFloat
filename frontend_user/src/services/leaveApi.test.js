import { createLeaveRequest } from './leaveApi';
import { getAuthToken, refreshAuthToken } from './authStorage';

jest.mock('./authStorage', () => ({
  getAuthToken: jest.fn(),
  refreshAuthToken: jest.fn(),
}));

const jsonResponse = (status, payload) => ({
  status,
  ok: status >= 200 && status < 300,
  headers: { get: () => 'application/json' },
  json: async () => payload,
});

beforeEach(() => {
  jest.clearAllMocks();
});

afterEach(() => {
  jest.restoreAllMocks();
});

test('refreshes an expired token and retries leave submission once', async () => {
  let token = 'expired-token';
  getAuthToken.mockImplementation(() => token);
  refreshAuthToken.mockImplementation(async () => {
    token = 'fresh-token';
    return true;
  });
  jest.spyOn(global, 'fetch')
    .mockResolvedValueOnce(jsonResponse(401, { msg: 'Token has expired' }))
    .mockResolvedValueOnce(jsonResponse(201, { data: { id: 123 } }));

  await expect(createLeaveRequest({ reason: 'Annual rest' }))
    .resolves.toMatchObject({ data: { id: 123 } });

  expect(refreshAuthToken).toHaveBeenCalledTimes(1);
  expect(global.fetch).toHaveBeenCalledTimes(2);
  expect(global.fetch.mock.calls[1][1].headers.Authorization).toBe('Bearer fresh-token');
});

test('shows the backend authentication error when token refresh is unavailable', async () => {
  getAuthToken.mockReturnValue('expired-token');
  refreshAuthToken.mockResolvedValue(false);
  jest.spyOn(global, 'fetch').mockResolvedValue(
    jsonResponse(401, { msg: 'Missing Authorization Header' }),
  );

  await expect(createLeaveRequest({ reason: 'Annual rest' }))
    .rejects.toThrow('Missing Authorization Header');

  expect(global.fetch).toHaveBeenCalledTimes(1);
});