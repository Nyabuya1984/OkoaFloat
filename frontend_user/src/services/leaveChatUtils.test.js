import { getManagerChatPeers } from './leaveChatUtils';

describe('getManagerChatPeers', () => {
  const users = [
    { id: 1, name: 'Same department manager', role: 'MANAGER', department_id: 10 },
    { id: 2, name: 'Legacy department manager', role: 'manager', department: 'Operations' },
    { id: 3, name: 'Other department manager', role: 'manager', department_id: 11, department: 'Finance' },
    { id: 4, name: 'Operations employee', role: 'employee', department: 'Operations' },
    { id: 5, name: 'Manager with canonical department name', role: 'manager', department_name: 'Operations' },
  ];

  test('includes managers matched by department ID or department name', () => {
    expect(getManagerChatPeers(users, {
      role: 'manager',
      department: 'Operations',
      departmentId: 10,
    }).map((peer) => peer.id)).toEqual([1, 2, 5]);
  });

  test('includes only a specifically assigned manager outside the department match', () => {
    expect(getManagerChatPeers(users, {
      role: 'manager',
      department: 'Operations',
      departmentId: 10,
      peerId: 3,
    }).map((peer) => peer.id)).toEqual([1, 2, 3, 5]);
  });

  test('does not offer employees or managers from unrelated departments as fallback peers', () => {
    expect(getManagerChatPeers(users, {
      role: 'manager',
      department: 'Operations',
      departmentId: 99,
    }).map((peer) => peer.id)).toEqual([2, 5]);
  });
});
