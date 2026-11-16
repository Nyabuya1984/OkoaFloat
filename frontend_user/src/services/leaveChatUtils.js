const normalizeDepartment = (value) => String(value || '').trim().toLowerCase();

export const getManagerChatPeers = (users, target) => {
  if (target?.role !== 'manager') return users;

  const targetDepartmentId = Number(target.departmentId);
  const hasTargetDepartmentId = Number.isFinite(targetDepartmentId) && targetDepartmentId > 0;
  const targetDepartment = normalizeDepartment(target.department);

  return users.filter((peer) => {
    if (String(peer.role || '').trim().toLowerCase() !== 'manager') return false;

    // A specifically assigned manager can be contacted even if their profile has
    // incomplete department metadata.
    if (target.peerId && Number(peer.id) === Number(target.peerId)) return true;

    const peerDepartmentId = Number(peer.department_id);
    const hasPeerDepartmentId = Number.isFinite(peerDepartmentId) && peerDepartmentId > 0;
    const sameDepartmentId = hasTargetDepartmentId
      && hasPeerDepartmentId
      && peerDepartmentId === targetDepartmentId;
    const peerDepartment = normalizeDepartment(peer.department_name || peer.department);
    const sameDepartmentName = targetDepartment && peerDepartment === targetDepartment;
    // Use names as a legacy-data fallback only when one side has no department ID;
    // conflicting IDs are authoritative and must not introduce unrelated peers.
    return Boolean(
      sameDepartmentId
      || ((!hasTargetDepartmentId || !hasPeerDepartmentId) && sameDepartmentName),
    );
  });
};
