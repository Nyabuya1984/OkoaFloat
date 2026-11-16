import React from 'react';
import {
  Area,
  AreaChart,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
} from 'recharts';

const outcomeColors = {
  phone_off: '#c2610c',
  no_answer: '#b45909',
  negotiation: '#be6212',
  wrong_number: '#9d5617',
  promise_to_pay: '#a04f08',
  callback_requested: '#c27d41',
  full_payment: '#9a5112',
  partial_payment: '#d4690b',
};
const outcomeNames = {
  phone_off: 'Phone off / unreachable',
  no_answer: 'No answer',
  negotiation: 'Negotiation',
  wrong_number: 'Wrong number',
  promise_to_pay: 'Promise to pay',
  callback_requested: 'Callback requested',
  full_payment: 'Full payment',
  partial_payment: 'Partial payment',
};
const money = (value) => new Intl.NumberFormat('en-KE', {
  style: 'currency',
  currency: 'KES',
  maximumFractionDigits: 0,
}).format(Number(value) || 0);

export default function CollectorAnalyticsPanel({ analytics }) {
  const breakdown = Object.entries(analytics?.interaction_breakdown || {})
    .map(([key, value]) => ({
      key,
      name: outcomeNames[key] || key,
      value: Number(value),
      color: outcomeColors[key] || '#78716c',
    }))
    .filter((item) => item.value > 0);
  const totalCalls = breakdown.reduce((sum, item) => sum + item.value, 0);
  const trend = (analytics?.daily_recovery_trend || []).map((item) => ({
    date: new Date(`${item.date}T00:00:00`).toLocaleDateString(undefined, { weekday: 'short' }),
    amount: Number(item.amount),
  }));
  const assigned = Number(analytics?.total_assigned || 0);
  const contacted = Number(analytics?.total_contacted || 0);
  const progress = assigned ? Math.round((contacted / assigned) * 100) : 0;

  return (
    <aside className="collector-analytics">
      <section className="collector-panel collector-chart-panel">
        <div className="collector-panel-heading">
          <div><h3>Interaction breakdown</h3><p>Call outcomes across your portfolio</p></div>
        </div>
        <div className="collector-donut-wrap">
          <ResponsiveContainer width="100%" height={154}>
            <PieChart>
              <Pie data={breakdown} dataKey="value" nameKey="name" innerRadius={48} outerRadius={68} paddingAngle={2} stroke="none">
                {breakdown.map((item) => <Cell key={item.key} fill={item.color} />)}
              </Pie>
              <Tooltip />
            </PieChart>
          </ResponsiveContainer>
          <div className="collector-donut-total"><strong>{totalCalls}</strong><span>calls</span></div>
        </div>
        {breakdown.length > 0 && (
          <div className="collector-chart-legend">
            {breakdown.map((item) => (
              <span key={item.key}><i style={{ backgroundColor: item.color }} />{item.name}<strong>{item.value}</strong></span>
            ))}
          </div>
        )}
        {breakdown.length === 0 && <p className="collector-chart-empty">Your call outcomes will appear here.</p>}
      </section>

      <section className="collector-panel collector-chart-panel">
        <div className="collector-panel-heading">
          <div><h3>Recovery trend</h3><p>Payments received · last 7 days</p></div>
        </div>
        <div className="collector-recovery-chart">
          <ResponsiveContainer width="100%" height={124}>
            <AreaChart data={trend} margin={{ top: 7, right: 2, left: 2, bottom: 0 }}>
              <defs>
                <linearGradient id="collectorRecoveryFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#c2610c" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#c2610c" stopOpacity={0.015} />
                </linearGradient>
              </defs>
              <XAxis dataKey="date" tickLine={false} axisLine={{ stroke: '#e8e2dc' }} tick={{ fill: '#787878', fontSize: 10 }} />
              <Tooltip formatter={(value) => money(value)} />
              <Area type="monotone" dataKey="amount" stroke="#c2610c" strokeWidth={2} fill="url(#collectorRecoveryFill)" />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </section>

      <section className="collector-panel collector-chart-panel">
        <div className="collector-progress-heading"><h3>Daily progress</h3><strong>{progress}%</strong></div>
        <div className="collector-progress-track collector-progress-track-warm" role="progressbar" aria-valuenow={progress} aria-valuemin="0" aria-valuemax="100" aria-label="Contacted accounts">
          <span style={{ width: `${progress}%` }} />
        </div>
        <div className="collector-progress-legend"><span>{contacted} contacted</span><span>{Number(analytics?.total_pending || 0)} pending</span></div>
      </section>
    </aside>
  );
}
