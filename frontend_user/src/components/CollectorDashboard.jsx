import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { AlertCircle, CheckCircle2, Clock3, PhoneCall, Wallet } from 'lucide-react';
import apiClient from '../services/debtCollectionApi';
import CompactKpiCard from './CompactKpiCard';
import CollectorAnalyticsPanel from './CollectorAnalyticsPanel';
import CollectorInteractionTable from './CollectorInteractionTable';
import LogInteractionModal from './LogInteractionModal';
import SmartDebtorTable from './SmartDebtorTable';

const emptyAnalytics = {
  total_assigned: 0,
  total_contacted: 0,
  total_pending: 0,
  recovered_today: '0',
  interaction_breakdown: {},
  daily_recovery_trend: [],
};
const money = (value) => new Intl.NumberFormat('en-KE', {
  style: 'currency',
  currency: 'KES',
  maximumFractionDigits: 0,
}).format(Number(value) || 0);

export default function CollectorDashboard({ compact = false, teamMode = false }) {
  const [records, setRecords] = useState([]);
  const [analytics, setAnalytics] = useState(emptyAnalytics);
  const [followUps, setFollowUps] = useState([]);
  const [selectedLoan, setSelectedLoan] = useState(null);
  const [search, setSearch] = useState('');
  const [now, setNow] = useState(Date.now());
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const dashboardRequestInProgress = useRef(false);

  const loadDashboard = useCallback(async ({ silent = false } = {}) => {
    if (dashboardRequestInProgress.current) return;
    dashboardRequestInProgress.current = true;
    if (!silent) setLoading(true);
    else setRefreshing(true);
    try {
      const [portfolioResponse, analyticsResponse, followUpsResponse] = await Promise.all([
        apiClient.get('/api/collector/my-portfolio'),
        apiClient.get('/api/collector/analytics'),
        apiClient.get('/api/debt-collection/follow-ups'),
      ]);
      setRecords(portfolioResponse.data.data || []);
      setAnalytics({ ...emptyAnalytics, ...(analyticsResponse.data.data || {}) });
      setFollowUps(followUpsResponse.data.data || []);
      setError('');
    } catch (loadError) {
      setError(loadError.message || 'Unable to load your collector portfolio.');
    } finally {
      if (!silent) setLoading(false);
      else setRefreshing(false);
      dashboardRequestInProgress.current = false;
    }
  }, []);

  useEffect(() => { loadDashboard(); }, [loadDashboard]);
  useEffect(() => {
    const refreshWhenVisible = () => {
      if (document.visibilityState === 'visible') loadDashboard({ silent: true });
    };
    const timer = window.setInterval(refreshWhenVisible, 30_000);
    window.addEventListener('focus', refreshWhenVisible);
    document.addEventListener('visibilitychange', refreshWhenVisible);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener('focus', refreshWhenVisible);
      document.removeEventListener('visibilitychange', refreshWhenVisible);
    };
  }, [loadDashboard]);
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 60_000);
    return () => window.clearInterval(timer);
  }, []);

  const orderedRecords = useMemo(
    () => [...records].sort((first, second) => Number(Boolean(first.last_interaction)) - Number(Boolean(second.last_interaction))),
    [records],
  );

  const saveInteraction = async (payload) => {
    setSaving(true);
    setMessage('');
    try {
      const response = await apiClient.post(
        `/api/debt-collection/loans/${selectedLoan.id}/calls`,
        payload,
      );
      const result = response.data.data;
      setRecords((current) => current.map((record) => (
        record.id === selectedLoan.id
          ? {
            ...result.loan,
            last_interaction: result.call,
            interactions: [result.call, ...(record.interactions || []).filter((call) => call.id !== result.call.id)],
          }
          : record
      )));
      setAnalytics((current) => {
        const firstContact = !records.find((record) => record.id === selectedLoan.id)?.last_interaction;
        const nextBreakdown = {
          ...current.interaction_breakdown,
          [result.call.outcome]: Number(current.interaction_breakdown[result.call.outcome] || 0) + 1,
        };
        const payment = Number(result.call.amount_paid || 0);
        const trend = current.daily_recovery_trend.map((day) => (
          day.date === result.call.created_at.slice(0, 10)
            ? { ...day, amount: String(Number(day.amount || 0) + payment) }
            : day
        ));
        return {
          ...current,
          total_contacted: Math.min(current.total_assigned, Number(current.total_contacted) + (firstContact ? 1 : 0)),
          total_pending: Math.max(0, Number(current.total_pending) - (firstContact ? 1 : 0)),
          recovered_today: String(Number(current.recovered_today || 0) + payment),
          interaction_breakdown: nextBreakdown,
          daily_recovery_trend: trend,
          interactions: [result.call, ...(current.interactions || []).filter((call) => call.id !== result.call.id)],
        };
      });
      try {
        const followUpsResponse = await apiClient.get('/api/debt-collection/follow-ups');
        setFollowUps(followUpsResponse.data.data || []);
      } catch (followUpError) {
        setError(followUpError.message || 'Interaction saved, but follow-ups could not be refreshed.');
      }
      setMessage('Interaction saved. Portfolio updated.');
      setSelectedLoan(null);
    } catch (saveError) {
      throw new Error(saveError.message || 'Unable to save this interaction.');
    } finally {
      setSaving(false);
    }
  };

  const completeFollowUp = async (followUpId) => {
    try {
      await apiClient.patch(`/api/debt-collection/follow-ups/${followUpId}`, { status: 'Completed' });
      setFollowUps((current) => current.filter((item) => item.id !== followUpId));
      setMessage('Follow-up marked complete.');
    } catch (followUpError) {
      setError(followUpError.message || 'Unable to update this follow-up.');
    }
  };

  return (
    <section className={`collector-dashboard ${compact ? 'collector-dashboard-compact' : ''}`} id="debt-collection">
      {error && <div className="leave-alert error" role="alert"><AlertCircle size={16} />{error}</div>}
      {message && <div className="leave-alert info" role="status"><CheckCircle2 size={16} />{message}</div>}

      <CollectorInteractionTable
        interactions={analytics.interactions || []}
        loading={loading}
        onRefresh={loadDashboard}
        onLogCall={(loanId) => {
          const loan = records.find((record) => record.id === loanId);
          if (loan?.is_assigned_to_me !== false) setSelectedLoan(loan);
        }}
      />

      <div className="collector-kpi-grid">
        <CompactKpiCard label="Total assigned" value={analytics.total_assigned} tone="blue" icon={PhoneCall} />
        <CompactKpiCard label="Contacted" value={analytics.total_contacted} tone="amber" icon={CheckCircle2} />
        <CompactKpiCard label="Pending contact" value={analytics.total_pending} tone="gray" icon={Clock3} />
        <CompactKpiCard label="Recovered today" value={money(analytics.recovered_today)} tone="green" icon={Wallet} />
      </div>

      <CollectorAnalyticsPanel analytics={analytics} />

      {loading ? (
        <div className="collector-loading" role="status">Loading your portfolio…</div>
      ) : (
        <div className="collector-workspace-grid collector-workspace-single">
          <SmartDebtorTable
            records={orderedRecords}
            search={search}
            onSearch={setSearch}
            onLogCall={(record) => {
              if (record?.is_assigned_to_me !== false) setSelectedLoan(record);
            }}
            onRefresh={() => loadDashboard({ silent: true })}
            refreshing={refreshing}
            teamMode={teamMode}
          />
        </div>
      )}

      {!loading && (
        <section className="collector-panel collector-follow-ups">
            <div className="collector-panel-heading"><div><h3>Promised payments and callbacks</h3><p>Pending follow-ups resurface when due.</p></div></div>
            {followUps.length === 0 ? <p className="collector-follow-up-empty">No pending follow-ups.</p> : (
              <div className="collector-follow-up-list">
                {followUps.map((item) => {
                  const due = new Date(item.due_at);
                  const isDue = due.getTime() <= now;
                  return (
                    <article key={item.id} className={isDue ? 'collector-follow-up-due' : ''}>
                      <div>
                        <strong>{item.debtor?.first_name} {item.debtor?.other_names} · {item.debtor?.business_name}</strong>
                        <span>{item.follow_up_type} · {due.toLocaleString()}</span>
                        <small>{isDue ? 'Due now' : 'Scheduled'}</small>
                      </div>
                      <button type="button" className="leave-secondary-button" onClick={() => completeFollowUp(item.id)}>Mark complete</button>
                    </article>
                  );
                })}
              </div>
            )}
        </section>
      )}

      {selectedLoan && (
        <LogInteractionModal
          loan={selectedLoan}
          onClose={() => !saving && setSelectedLoan(null)}
          onSave={saveInteraction}
        />
      )}
    </section>
  );
}
