import React from 'react';

export const ComplianceBadge = ({ status = 'neutral' }) => { const labels = { compliant: 'Compliant', 'at-risk': 'At risk', breached: 'Breached', neutral: 'No target' }; return <span className={`sales-v2-badge sales-v2-badge-${status}`} role="status">{labels[status] || labels.neutral}</span>; };
