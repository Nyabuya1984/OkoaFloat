import React from 'react';

export const AgentPicker = ({ value, onChange }) => <label className="sales-v2-agent-picker">Agent search<input value={value} onChange={(event) => onChange(event.target.value)} placeholder="Search agent" aria-label="Search agent" /></label>;
