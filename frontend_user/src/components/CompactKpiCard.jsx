import React from 'react';

export default function CompactKpiCard({ label, value, tone, icon: Icon }) {
  return (
    <article className={`collector-kpi collector-kpi-${tone}`}>
      <span className="collector-kpi-icon"><Icon size={16} aria-hidden="true" /></span>
      <div className="collector-kpi-copy">
        <span>{label}</span>
        <strong>{value}</strong>
      </div>
    </article>
  );
}
