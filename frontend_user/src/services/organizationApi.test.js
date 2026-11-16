import { organizationApi } from './organizationApi';

jest.mock('./authStorage', () => ({
  getAuthToken: () => 'access-token',
  refreshAuthToken: jest.fn().mockResolvedValue(false),
}));

afterEach(() => {
  jest.restoreAllMocks();
});

test('preserves the authentication error from the live locations API', async () => {
  jest.spyOn(global, 'fetch').mockResolvedValue({
    status: 401,
    ok: false,
    json: async () => ({ msg: 'Missing Authorization Header' }),
  });

  await expect(organizationApi.getLiveLocations())
    .rejects.toMatchObject({
      message: 'Missing Authorization Header',
      status: 401,
    });
});

test('preserves the authentication error from the live location stream', async () => {
  jest.spyOn(global, 'fetch').mockResolvedValue({
    status: 401,
    ok: false,
    json: async () => ({ msg: 'Missing Authorization Header' }),
  });

  await expect(
    organizationApi.streamLiveLocations(jest.fn(), new AbortController().signal),
  ).rejects.toThrow('Missing Authorization Header');
});
