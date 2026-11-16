import React, { useCallback, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { apiUrl } from '../services/apiConfig';
import { getAuthToken } from '../services/authStorage';
import LogInteractionModal from './LogInteractionModal';
import apiClient from '../services/debtCollectionApi';
import CollectorDashboard from './CollectorDashboard';
import CollectorInteractionTable from './CollectorInteractionTable';
import ClientProfileLookup from './ClientProfileLookup';
import { downloadDebtCollectionTemplate } from '../services/debtCollectionFiles';
import DebtCollectionImportStatus from './DebtCollectionImportStatus';

const statusLabels = {
  active: 'Active',
  overdue: 'Overdue',
  in_negotiation: 'In Negotiation',
  promise_to_pay: 'Promise to Pay',
  settled: 'Settled',
  written_off: 'Written Off',
  legal: 'Legal',
};

const formatMoney = (value) => {
  const number = Number(value || 0);
  return new Intl.NumberFormat('en-KE', { style: 'currency', currency: 'KES', maximumFractionDigits: 0 }).format(number);
};

const formatTableDate = (value) => {
  if (!value) return '-';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleDateString();
};

const apiErrorMessage = (error, fallback) => error.response?.data?.error?.message || error.message || fallback;

const emptySummary = { total_outstanding: 0, active_accounts: 0, overdue_accounts: 0, recovered_to_date: 0, records: [], permissions: {} };
const emptyDebtor = { first_name: '', other_names: '', agent_msisdn: '', owner_msisdn: '', operator_msisdn: '', agent_no: '', store_number: '', business_name: '', location: '' };
const emptyLoan = { loan_amount: '', loan_date: '', amount_paid: '0', status: 'active', last_interest_calc_date: '', no_of_days: '0' };
const outcomes = [
  ['phone_off', 'Phone off / client unreachable'],
  ['no_answer', 'Ringing, no answer'],
  ['negotiation', 'Negotiation'],
  ['wrong_number', 'Wrong number'],
  ['promise_to_pay', 'Promise to pay'],
  ['callback_requested', 'Call back requested'],
  ['full_payment', 'Full payment'],
  ['partial_payment', 'Partial payment'],
];

const DebtEntryDetails = ({ record }) => {
  const fields = [
    ['First name', record.first_name],
    ['Other names', record.other_names],
    ['Agent phone', record.agent_number],
    ['Owner phone', record.owner_msisdn],
    ['Operator phone', record.operator_msisdn],
    ['Agent number', record.agent_no],
    ['Store number', record.store_number],
    ['Business name', record.business_name],
    ['Location', record.business_location],
    ['Loan amount', formatMoney(record.loan_amount)],
    ['Loan balance', formatMoney(record.loan_balance)],
    ['Amount paid', formatMoney(record.amount_paid)],
    ['Status', statusLabels[record.status] || record.status],
    ['Loan date', record.loan_date],
    ['Created at', record.created_at ? new Date(record.created_at).toLocaleString() : ''],
    ['Last interest calculation', record.last_interest_calc_date],
    ['Days since issue', record.no_of_days],
  ];

  return (
    <section className="debt-entry-details" aria-label="Debtor and loan details">
      <strong>Entry details</strong>
      <dl className="debt-record-detail-grid">
        {fields.map(([label, value]) => (
          <div key={label}><dt>{label}</dt><dd>{value === null || value === undefined || value === '' ? '-' : value}</dd></div>
        ))}
      </dl>
    </section>
  );
};

export default function DebtCollectionPage({ compact = false }) {
  const [summary, setSummary] = useState(emptySummary);
  const [permissionsLoaded, setPermissionsLoaded] = useState(false);
  const [loading, setLoading] = useState(true);
  const [recordsLoading, setRecordsLoading] = useState(true);
  const [analyticsLoading, setAnalyticsLoading] = useState(true);
  const [error, setError] = useState('');
  const [recordsError, setRecordsError] = useState('');
  const [supplementalError, setSupplementalError] = useState('');
  const [message, setMessage] = useState('');
  const [messageType, setMessageType] = useState('success');
  const [collectors, setCollectors] = useState([]);
  const [followUps, setFollowUps] = useState([]);
  const [analytics, setAnalytics] = useState(null);
  const [analyticsDates, setAnalyticsDates] = useState({ from: '', to: '' });
  const [analyticsCollectorId, setAnalyticsCollectorId] = useState('');
  const [performance, setPerformance] = useState(null);
  const [filters, setFilters] = useState({ q: '', agent_name: '', agent_number: '', business_name: '', status: '', location: '', store_number: '', min_balance: '', max_balance: '', overdue_days: '', collector_id: '', collector_capacity: '' });
  const [appliedFilters, setAppliedFilters] = useState('');
  const [selectedLoans, setSelectedLoans] = useState([]);
  const [portfolioSort, setPortfolioSort] = useState({ key: 'agent_name', direction: 'asc' });
  const [archiveView, setArchiveView] = useState(false);
  const [archiving, setArchiving] = useState(false);
  const [recordPanel, setRecordPanel] = useState(null);
  const [multiViewOpen, setMultiViewOpen] = useState(false);
  const [recordFeedback, setRecordFeedback] = useState(null);
  const [dailyReportsExpanded, setDailyReportsExpanded] = useState(!compact);
  const [collectorId, setCollectorId] = useState('');
  const [assignmentReason, setAssignmentReason] = useState('');
  const [distributionOpen, setDistributionOpen] = useState(false);
  const [debtor, setDebtor] = useState(emptyDebtor);
  const [selectedClientProfile, setSelectedClientProfile] = useState(null);
  const [clientProfileConfirmed, setClientProfileConfirmed] = useState(false);
  const [loan, setLoan] = useState(emptyLoan);
  const [importIssues, setImportIssues] = useState([]);
  const [importing, setImporting] = useState(false);
  const [importFile, setImportFile] = useState(null);
  const [importStatus, setImportStatus] = useState('');
  const [importProgress, setImportProgress] = useState(0);
  const [importFeedback, setImportFeedback] = useState('');
  const importInput = useRef(null);
  const loadSequence = useRef(0);
  const [openCalls, setOpenCalls] = useState(null);
  const [logInteractionLoan, setLogInteractionLoan] = useState(null);
  const [callLogs, setCallLogs] = useState({});
  const [loadingCallLogs, setLoadingCallLogs] = useState({});
  const [callDrafts, setCallDrafts] = useState({});
  const [debtorEdits, setDebtorEdits] = useState({});
  const [loanEdits, setLoanEdits] = useState({});
  const [ratingDrafts, setRatingDrafts] = useState({});
  const [writeOffReasons, setWriteOffReasons] = useState({});
  const records = summary.records || [];
  const sortedRecords = [...records].sort((first, second) => {
    const firstValue = first[portfolioSort.key];
    const secondValue = second[portfolioSort.key];
    const firstEmpty = firstValue === null || firstValue === undefined || firstValue === '';
    const secondEmpty = secondValue === null || secondValue === undefined || secondValue === '';
    if (firstEmpty || secondEmpty) return firstEmpty === secondEmpty ? 0 : firstEmpty ? 1 : -1;
    const numericSort = ['loan_amount', 'amount_paid', 'loan_balance'].includes(portfolioSort.key);
    const comparison = numericSort
      ? Number(firstValue) - Number(secondValue)
      : String(firstValue).localeCompare(String(secondValue), undefined, {
        numeric: true,
        sensitivity: 'base',
      });
    return portfolioSort.direction === 'asc' ? comparison : -comparison;
  });
  const sortPortfolioBy = (key) => setPortfolioSort((current) => ({
    key,
    direction: current.key === key && current.direction === 'asc' ? 'desc' : 'asc',
  }));
  const portfolioSortHeader = (label, key) => (
    <button
      type="button"
      className="debt-sort-button"
      aria-label={`Sort by ${label}`}
      data-sort-direction={portfolioSort.key === key ? portfolioSort.direction : 'none'}
      onClick={() => sortPortfolioBy(key)}
    >
      {label}
    </button>
  );
  const portfolioAriaSort = (key) => (
    portfolioSort.key === key ? (portfolioSort.direction === 'asc' ? 'ascending' : 'descending') : 'none'
  );
  const listedDebtorCount = new Set(
    records.map((record) => record.debtor_id ?? record.id).filter(Boolean),
  ).size;
  const selectedRecord = selectedLoans.length === 1
    ? records.find((item) => item.id === selectedLoans[0])
    : null;
  const selectedRecords = records.filter((item) => selectedLoans.includes(item.id));
  const canManage = Boolean(summary.permissions?.can_manage);
  const canViewAll = Boolean(summary.permissions?.can_view_all);
  const canViewAllDebtors = Boolean(summary.permissions?.can_view_all_debtors);
  const canViewTeam = Boolean(summary.permissions?.can_view_team);
  const isGeneralManagerView = Boolean(summary.permissions?.is_general_manager);
  const canPermanentlyDelete = Boolean(summary.permissions?.can_permanently_delete);
  const canEditRecords = canManage || canPermanentlyDelete;
  const canSelectLoans = canManage || canPermanentlyDelete || canViewAll || canViewTeam;
  const selectedHaveAssignments = records.some((item) => selectedLoans.includes(item.id) && item.collector_id);
  const allocationCollectors = filters.collector_capacity === ''
    ? collectors
    : collectors.filter((collector) => collector.active_accounts <= Number(filters.collector_capacity));

  const showMessage = (text, type = 'success') => {
    setMessageType(type);
    setMessage(text);
  };

  const setDebtorField = (field) => (event) => {
    setClientProfileConfirmed(false);
    setDebtor((current) => ({ ...current, [field]: event.target.value }));
  };

  const loadData = useCallback(async (query = appliedFilters) => {
    const requestId = ++loadSequence.current;
    setLoading(true);
    setRecordsLoading(true);
    setAnalyticsLoading(true);
    setError('');
    setRecordsError('');
    setSupplementalError('');
    try {
      const headers = { Authorization: `Bearer ${getAuthToken()}` };
      const loansEndpoint = archiveView
        ? `/api/debt-collection/loans/archived${query ? `?${query}` : ''}`
        : `/api/debt-collection/loans${query ? `?${query}` : ''}`;
      const summaryResponse = await apiClient.get(
        '/api/debt-collection/summary?include_records=false',
        { headers },
      );
      if (requestId !== loadSequence.current) return;
      const summaryData = summaryResponse.data.data || {};
      setSummary({ ...emptySummary, ...summaryData, records: [] });
      setPermissionsLoaded(true);
      setLoading(false);

      const permissions = summaryData.permissions || {};
      if (!permissions.can_manage && !permissions.can_view_all && !permissions.can_view_team) {
        setRecordsLoading(false);
        setAnalyticsLoading(false);
        return;
      }

      const loansPromise = apiClient.get(loansEndpoint, { headers }).then(
        (response) => ({ records: response.data.data || [], error: '' }),
        (err) => ({ records: null, error: apiErrorMessage(err, 'Unable to load debt collection accounts.') }),
      );
      const supplementalPromise = (async () => {
        try {
          if (permissions.can_manage) {
            const [collectorsResponse, analyticsResponse, followUpsResponse] = await Promise.all([
              apiClient.get('/api/debt-collection/collectors', { headers }),
              apiClient.get('/api/debt-collection/analytics', { headers }),
              apiClient.get('/api/debt-collection/follow-ups', { headers }),
            ]);
            if (requestId === loadSequence.current) {
              setCollectors(collectorsResponse.data.data || []);
              setAnalytics(analyticsResponse.data.data || null);
              setFollowUps(followUpsResponse.data.data || []);
            }
          } else {
            const [analyticsResponse, followUpsResponse] = await Promise.all([
              apiClient.get('/api/debt-collection/analytics', { headers }),
              apiClient.get('/api/debt-collection/follow-ups', { headers }),
            ]);
            if (requestId === loadSequence.current) {
              setAnalytics(analyticsResponse.data.data || null);
              setFollowUps(followUpsResponse.data.data || []);
              setPerformance(null);
            }
          }
        } catch (err) {
          if (requestId === loadSequence.current) {
            setSupplementalError(apiErrorMessage(err, 'Unable to load debt collection reports.'));
          }
        } finally {
          if (requestId === loadSequence.current) setAnalyticsLoading(false);
        }
      })();
      const loanResult = await loansPromise;
      if (requestId === loadSequence.current) {
        if (loanResult.error) {
          setRecordsError(loanResult.error);
        } else {
          setSummary((current) => ({ ...current, records: loanResult.records }));
        }
        setRecordsLoading(false);
      }
      await supplementalPromise;
    } catch (err) {
      if (requestId === loadSequence.current) {
        setError(apiErrorMessage(err, 'Unable to load debt collection data.'));
      }
    } finally {
      if (requestId === loadSequence.current) {
        setLoading(false);
        setRecordsLoading(false);
        setAnalyticsLoading(false);
      }
    }
  }, [appliedFilters, archiveView]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const request = async (path, options = {}) => {
    const response = await apiClient.request({ url: apiUrl(path),
      ...options,
      data: options.body instanceof FormData || typeof options.body !== 'string' ? options.body : JSON.parse(options.body),
      headers: { Authorization: `Bearer ${getAuthToken()}`, ...(options.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }), ...options.headers },
    });
    const payload = response.data;
    return payload?.data;
  };

  const submitDebtor = async (event) => {
    event.preventDefault();
    showMessage('');
    if (selectedClientProfile && !clientProfileConfirmed) {
      showMessage('Confirm the selected client profile before saving.', 'error');
      return;
    }
    try {
      const created = await request('/api/debt-collection/debtors', { method: 'POST', body: JSON.stringify(debtor) });
      if (loan.loan_amount) {
        await request('/api/debt-collection/loans', { method: 'POST', body: JSON.stringify({ ...loan, debtor_id: created.id }) });
      }
      setDebtor(emptyDebtor);
      setLoan(emptyLoan);
      setSelectedClientProfile(null);
      setClientProfileConfirmed(false);
      showMessage('Debtor and loan saved.');
      await loadData();
    } catch (err) {
      showMessage(err.message, 'error');
    }
  };

  const confirmClientProfile = (match) => {
    const [firstName = '', ...remainingNames] = String(match.agent_name || '').trim().split(/\s+/);
    setDebtor((current) => ({
      ...current,
      first_name: firstName || current.first_name,
      other_names: remainingNames.join(' ') || current.other_names,
      owner_msisdn: match.owner_phone_number || current.owner_msisdn,
      agent_no: match.agent_number || current.agent_no,
      store_number: match.store_number || current.store_number,
      business_name: match.agent_name || current.business_name,
      location: match.business_location || current.location,
    }));
    setSelectedClientProfile(match);
    setClientProfileConfirmed(true);
  };

  const assignSelected = async (event) => {
    event.preventDefault();
    if (!collectorId || selectedLoans.length === 0) return;
    const selectedHaveAssignments = records.some((item) => selectedLoans.includes(item.id) && item.collector_id);
    if (selectedHaveAssignments && !assignmentReason.trim()) {
      showMessage('A reason is required when reassigning accounts.', 'error');
      return;
    }
    try {
      const result = await request('/api/debt-collection/assignments/bulk', { method: 'POST', body: JSON.stringify({ collector_id: Number(collectorId), loan_ids: selectedLoans, reason: assignmentReason.trim() || undefined }) });
      const collector = collectors.find((item) => item.id === Number(collectorId));
      showMessage(`${result.assigned} loan${result.assigned === 1 ? '' : 's'} allocated${collector ? ` to ${collector.full_name}` : ''}.`);
      setSelectedLoans([]);
      setCollectorId('');
      setAssignmentReason('');
      setDistributionOpen(false);
      await loadData();
    } catch (err) {
      showMessage(err.message, 'error');
    }
  };

  const assignLoan = async (loanId, newCollectorId) => {
    if (!newCollectorId) return;
    const currentLoan = records.find((item) => item.id === loanId);
    let reason;
    if (currentLoan?.collector_id) {
      reason = window.prompt('Enter a reason for reassigning this account:');
      if (reason === null) return;
      if (!reason.trim()) {
        showMessage('A reason is required when reassigning an account.', 'error');
        return;
      }
    }
    try {
      await request(`/api/debt-collection/loans/${loanId}/assignments`, {
        method: 'POST',
        body: JSON.stringify({ collector_id: Number(newCollectorId), reason: reason?.trim() }),
      });
      const collector = collectors.find((item) => item.id === Number(newCollectorId));
      showMessage(`Account assigned to ${collector?.full_name || 'collector'}.`);
      await loadData();
    } catch (err) {
      showMessage(err.message, 'error');
    }
  };

  const saveInteraction = async (loanId, payload) => {
    const result = await request(`/api/debt-collection/loans/${loanId}/calls`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    if (payload.outcome === 'partial_payment') {
      showMessage(`Partial payment recorded. Outstanding balance: ${formatMoney(result.loan.loan_balance)}.`);
    } else if (payload.outcome === 'full_payment') {
      showMessage('Full payment recorded. Outstanding balance: Ksh 0.');
    } else {
      showMessage('Client interaction recorded.');
    }
    if (openCalls === loanId) await loadCalls(loanId);
    await loadData();
  };

  const submitCall = async (event, loanId) => {
    event.preventDefault();
    const draft = callDrafts[loanId] || {};
    try {
      await request(`/api/debt-collection/loans/${loanId}/calls`, { method: 'POST', body: JSON.stringify(draft) });
      showMessage('Client interaction recorded.');
      setCallDrafts((current) => ({ ...current, [loanId]: { outcome: '', notes: '' } }));
      if (openCalls === loanId) await loadCalls(loanId);
      await loadData();
    } catch (err) {
      showMessage(err.message, 'error');
    }
  };

  const loadCalls = async (loanId) => {
    setLoadingCallLogs((current) => ({ ...current, [loanId]: true }));
    try {
      const rows = await request(`/api/debt-collection/loans/${loanId}/calls`);
      setCallLogs((current) => ({ ...current, [loanId]: rows || [] }));
    } catch (err) {
      showMessage(err.message, 'error');
    } finally {
      setLoadingCallLogs((current) => ({ ...current, [loanId]: false }));
    }
  };

  const toggleCalls = async (loanId) => {
    const next = openCalls === loanId ? null : loanId;
    setOpenCalls(next);
    if (next !== null) await loadCalls(loanId);
  };

  useEffect(() => {
    if (openCalls === null) return undefined;
    const closeOnEscape = (event) => {
      if (event.key === 'Escape') setOpenCalls(null);
    };
    window.addEventListener('keydown', closeOnEscape);
    return () => window.removeEventListener('keydown', closeOnEscape);
  }, [openCalls]);

  const saveDebtorDetails = async (event, item) => {
    event.preventDefault();
    try {
      const draft = debtorEdits[item.debtor_id] || item;
      await request(`/api/debt-collection/debtors/${item.debtor_id}`, {
        method: 'PATCH',
        body: JSON.stringify({
          first_name: draft.first_name,
          other_names: draft.other_names,
          agent_msisdn: draft.agent_number,
          owner_msisdn: draft.owner_msisdn,
          operator_msisdn: draft.operator_msisdn,
          agent_no: draft.agent_no,
          store_number: draft.store_number,
          business_name: draft.business_name,
          location: draft.business_location,
        }),
      });
      showMessage('Debtor details updated.');
      setRecordFeedback({ text: 'Client details updated.', type: 'info' });
      await loadData();
    } catch (err) {
      setRecordFeedback({ text: err.message, type: 'error' });
      showMessage(err.message, 'error');
    }
  };

  const updateDebtorEdit = (item, field, value) => setDebtorEdits((current) => ({
    ...current,
    [item.debtor_id]: { ...item, ...current[item.debtor_id], [field]: value },
  }));

  const saveLoanDetails = async (event, item) => {
    event.preventDefault();
    try {
      await request(`/api/debt-collection/loans/${item.id}`, { method: 'PATCH', body: JSON.stringify(loanEdits[item.id] || {}) });
      showMessage('Loan details updated.');
      setRecordFeedback({ text: 'Loan details updated.', type: 'info' });
      await loadData();
    } catch (err) {
      setRecordFeedback({ text: err.message, type: 'error' });
      showMessage(err.message, 'error');
    }
  };

  const restoreLoan = async (item) => {
    setArchiving(true);
    try {
      await request(`/api/debt-collection/loans/${item.id}/restore`, { method: 'POST' });
      showMessage('Account restored to the active portfolio.');
      setSelectedLoans((current) => current.filter((id) => id !== item.id));
      await loadData();
    } catch (err) {
      showMessage(err.message, 'error');
    } finally {
      setArchiving(false);
    }
  };

  const archiveSelectedLoans = async () => {
    if (!selectedLoans.length) return;
    if (!window.confirm(`Archive ${selectedLoans.length} selected account${selectedLoans.length === 1 ? '' : 's'}? You can restore them later.`)) return;
    setArchiving(true);
    try {
      const result = await request('/api/debt-collection/loans/archive/bulk', {
        method: 'POST',
        body: JSON.stringify({ loan_ids: selectedLoans }),
      });
      const archivedCount = Array.isArray(result) ? result.length : result.archived;
      showMessage(`${archivedCount} account${archivedCount === 1 ? '' : 's'} archived.`);
      setSelectedLoans([]);
      await loadData();
    } catch (err) {
      showMessage(err.message, 'error');
    } finally {
      setArchiving(false);
    }
  };

  const restoreSelectedLoans = async () => {
    if (!selectedLoans.length) return;
    setArchiving(true);
    try {
      const result = await request('/api/debt-collection/loans/restore/bulk', {
        method: 'POST',
        body: JSON.stringify({ loan_ids: selectedLoans }),
      });
      const restoredCount = Array.isArray(result) ? result.length : result.restored;
      showMessage(`${restoredCount} account${restoredCount === 1 ? '' : 's'} restored to the active portfolio.`);
      setSelectedLoans([]);
      await loadData();
    } catch (err) {
      showMessage(err.message, 'error');
    } finally {
      setArchiving(false);
    }
  };

  const submitRating = async (event, loanId) => {
    event.preventDefault();
    try {
      await request(`/api/debt-collection/loans/${loanId}/ratings`, { method: 'POST', body: JSON.stringify(ratingDrafts[loanId] || {}) });
      showMessage('Credit rating approved and recorded.');
      await loadData();
    } catch (err) {
      showMessage(err.message, 'error');
    }
  };

  const approveWriteOff = async (event, loanId) => {
    event.preventDefault();
    try {
      await request(`/api/debt-collection/loans/${loanId}/write-off`, { method: 'POST', body: JSON.stringify({ reason: writeOffReasons[loanId] }) });
      showMessage('Loan write-off approved.');
      await loadData();
    } catch (err) {
      showMessage(err.message, 'error');
    }
  };

  const importPortfolio = async () => {
    if (!importFile || importing) return;
    const formData = new FormData();
    formData.append('file', importFile);
    setImportIssues([]);
    setImportFeedback('');
    setImportProgress(0);
    setImporting(true);
    setImportStatus('uploading');
    try {
      const response = await apiClient.post(apiUrl('/api/debt-collection/import'), formData, {
        onUploadProgress: (event) => {
          if (!event.total) return;
          setImportProgress(Math.min(100, Math.round((event.loaded / event.total) * 100)));
          if (event.loaded >= event.total) setImportStatus('processing');
        },
      });
      const result = response.data?.data;
      if (!result) throw new Error('The server returned an invalid import response.');
      setImportIssues(result.issues || []);
      if (result.total_rows === 0) {
        setImportStatus('failed');
        setImportFeedback('Import failed: the selected file contains no data rows.');
      } else if (result.accepted_rows === 0) {
        setImportStatus('failed');
        setImportFeedback(`Import failed: none of the ${result.rejected_rows} rows were accepted.`);
      } else if (result.rejected_rows > 0) {
        setImportStatus('partial');
        setImportFeedback(`Import partially complete: ${result.accepted_rows} accepted, ${result.rejected_rows} rejected.`);
      } else {
        setImportStatus('success');
        setImportFeedback(`Import successful: ${result.accepted_rows} row${result.accepted_rows === 1 ? '' : 's'} imported.`);
      }
      await loadData();
    } catch (err) {
      setImportStatus('failed');
      setImportFeedback(apiErrorMessage(err, 'The file could not be imported.'));
    } finally {
      setImporting(false);
    }
  };

  const deleteLoanRecord = async (item) => {
    if (!window.confirm(`Delete the loan record for ${item.agent_name}? This is a soft delete and can be audited.`)) return;
    try {
      await request(`/api/debt-collection/loans/${item.id}`, { method: 'DELETE' });
      showMessage(`Loan record for ${item.agent_name} deleted.`);
      setSelectedLoans((current) => current.filter((id) => id !== item.id));
      setRecordPanel((current) => current?.loanId === item.id ? null : current);
      await loadData();
    } catch (err) {
      showMessage(err.message, 'error');
    }
  };

  const permanentlyDeleteLoanRecord = async (item) => {
    if (!window.confirm(`Permanently delete the loan entry for ${item.agent_name}? This cannot be undone.`)) return;
    try {
      await request(`/api/debt-collection/loans/${item.id}/permanent`, { method: 'DELETE' });
      showMessage(`Loan entry for ${item.agent_name} permanently deleted.`);
      setSelectedLoans((current) => current.filter((id) => id !== item.id));
      setRecordPanel((current) => current?.loanId === item.id ? null : current);
      await loadData();
    } catch (err) {
      showMessage(err.message, 'error');
    }
  };

  const permanentlyDeleteSelectedLoans = async () => {
    if (!selectedLoans.length) return;
    const count = selectedLoans.length;
    if (!window.confirm(`Permanently delete ${count} selected loan entr${count === 1 ? 'y' : 'ies'}? This cannot be undone.`)) return;
    setArchiving(true);
    try {
      const result = await request('/api/debt-collection/loans/permanent/bulk', {
        method: 'DELETE',
        body: JSON.stringify({ loan_ids: selectedLoans }),
      });
      const deletedCount = result.permanently_deleted;
      if (!Number.isInteger(deletedCount) || deletedCount !== count) {
        throw new Error('The server returned an invalid bulk-delete result.');
      }
      showMessage(`${deletedCount} loan entr${deletedCount === 1 ? 'y' : 'ies'} permanently deleted.`);
      setSelectedLoans([]);
      setRecordPanel(null);
      setOpenCalls(null);
      await loadData();
    } catch (err) {
      showMessage(err.message, 'error');
    } finally {
      setArchiving(false);
    }
  };

  const permanentlyDeleteClient = async (item) => {
    if (!window.confirm(`Permanently delete ${item.agent_name} and all of this client's loan and call records? This cannot be undone.`)) return;
    try {
      await request(`/api/debt-collection/debtors/${item.debtor_id}/permanent`, { method: 'DELETE' });
      showMessage(`Client record for ${item.agent_name} permanently deleted.`);
      setSelectedLoans((current) => current.filter((id) => id !== item.id));
      setRecordPanel((current) => current?.loanId === item.id ? null : current);
      await loadData();
    } catch (err) {
      showMessage(err.message, 'error');
    }
  };

  const chooseImportFile = (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    setImportFile(file);
    setImportStatus('');
    setImportFeedback('');
    setImportIssues([]);
    setImportProgress(0);
    event.target.value = '';
  };

  const handleImportAction = () => {
    if (importFile) importPortfolio();
    else importInput.current?.click();
  };

  const downloadPortfolio = async (format) => {
    try {
      if (appliedFilters) {
        const response = await apiClient.get(apiUrl(`/api/debt-collection/export.${format}?${appliedFilters}`), { responseType: 'blob' });
        const filteredUrl = URL.createObjectURL(response.data);
        const filteredLink = document.createElement('a');
        filteredLink.href = filteredUrl;
        filteredLink.download = `debt-portfolio.${format}`;
        filteredLink.click();
        URL.revokeObjectURL(filteredUrl);
        return;
      }
      const response = await fetch(apiUrl(`/api/debt-collection/export.${format}`), { headers: { Authorization: `Bearer ${getAuthToken()}` } });
      if (!response.ok) throw new Error('Unable to export the debt portfolio.');
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `debt-portfolio.${format}`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      showMessage(err.message, 'error');
    }
  };

  const filterAnalytics = async (event) => {
    event.preventDefault();
    const params = new URLSearchParams(Object.entries(analyticsDates).filter(([, value]) => value));
    if (analyticsCollectorId) params.set('collector_id', analyticsCollectorId);
    try {
      setAnalytics(await request(`/api/debt-collection/analytics${params.toString() ? `?${params}` : ''}`));
    } catch (err) {
      showMessage(err.message, 'error');
    }
  };

  const completeFollowUp = async (followUpId) => {
    try {
      await request(`/api/debt-collection/follow-ups/${followUpId}`, { method: 'PATCH', body: JSON.stringify({ status: 'Completed' }) });
      showMessage('Follow-up marked complete.');
      await loadData();
    } catch (err) {
      showMessage(err.message, 'error');
    }
  };

  const applyFilters = (event) => {
    event.preventDefault();
    const params = new URLSearchParams(Object.entries(filters).filter(([, value]) => value));
    setAppliedFilters(params.toString());
  };

  useEffect(() => {
    const timer = window.setTimeout(() => {
      const params = new URLSearchParams(Object.entries(filters).filter(([, value]) => value));
      setAppliedFilters(params.toString());
    }, 350);
    return () => window.clearTimeout(timer);
  }, [filters]);

  const updateCallDraft = (loanId, field, value) => setCallDrafts((current) => ({ ...current, [loanId]: { ...current[loanId], [field]: value } }));
  const openLoanFromReport = async (loanId) => {
    if (!loanId) return;
    await toggleCalls(loanId);
    window.setTimeout(() => {
      document.querySelector(`[data-loan-id="${loanId}"]`)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }, 0);
  };

  const openSelectedRecord = (mode, record = selectedRecord) => {
    if (!record) return;
    setSelectedLoans([record.id]);
    setRecordFeedback(null);
    if (mode === 'edit') {
      setDebtorEdits((current) => ({
        ...current,
        [record.debtor_id]: current[record.debtor_id] || {
          ...record,
          agent_number: record.agent_number || '',
          business_location: record.business_location || '',
        },
      }));
      setLoanEdits((current) => ({
        ...current,
        [record.id]: current[record.id] || {
          loan_amount: record.loan_amount,
          loan_date: record.loan_date || '',
          last_interest_calc_date: record.last_interest_calc_date || '',
          status: record.status,
        },
      }));
    }
    setMultiViewOpen(false);
    setRecordPanel({ loanId: record.id, mode });
  };

  if (!permissionsLoaded) {
    return (
      <section className="leave-section" id="debt-collection" aria-label="Debt collection">
        <div className="leave-section-heading"><div><p className="leave-kicker">COLLECTIONS</p><h2>Debt Collection</h2></div></div>
        {loading && <p className="leave-empty" role="status">Loading debt collection access…</p>}
        {!loading && (
          <div className="leave-alert error" role="alert">
            {error || 'Unable to determine debt collection access.'}
            <button type="button" className="leave-text-button" onClick={() => loadData()}>Retry</button>
          </div>
        )}
      </section>
    );
  }

  if (!canManage && !canViewAll && !canViewTeam) {
    return <CollectorDashboard compact={compact} teamMode={canViewTeam} />;
  }

  if (compact && !canManage && !canViewTeam) {
    return (
      <section className="leave-section" id="debt-collection" aria-label="Debt collection summary">
        <div className="leave-section-heading">
          <div>
            <p className="leave-kicker">COLLECTIONS</p>
            <h2>Debt Collection</h2>
          </div>
        </div>
        <div className="report-card-grid">
          <div className="report-card"><span>{canViewAll ? 'Total outstanding' : 'My total outstanding'}</span><strong>{formatMoney(summary.total_outstanding)}</strong></div>
          {!canManage && <div className="report-card"><span>Promises to pay today</span><strong>{performance?.periods?.daily?.promises_to_pay || 0}</strong></div>}
          {!canManage && <div className="report-card"><span>Recovered today</span><strong>{formatMoney(performance?.periods?.daily?.recovered)}</strong></div>}
          {canManage && <div className="report-card"><span>Active accounts</span><strong>{summary.active_accounts || 0}</strong></div>}
          {canManage && <div className="report-card"><span>Overdue</span><strong>{summary.overdue_accounts || 0}</strong></div>}
          {canManage && <div className="report-card"><span>Recovered</span><strong>{formatMoney(summary.recovered_to_date)}</strong></div>}
        </div>
        {canManage && !compact && (
          <CollectorInteractionTable
            interactions={analytics?.interactions || []}
            loading={analyticsLoading}
            onOpenLoan={openLoanFromReport}
            onImportClick={canManage ? handleImportAction : undefined}
            importReady={Boolean(importFile)}
            importing={importing}
          />
        )}
        <>
            {message && <div className={`leave-alert ${messageType === 'error' ? 'error' : 'info'}`} role={messageType === 'error' ? 'alert' : 'status'}>{message}</div>}
            {recordsLoading && <p className="leave-empty" role="status">Loading your assigned clients…</p>}
            {error && <div className="leave-alert error" role="alert">{error}</div>}
            {recordsError && <div className="leave-alert error" role="alert">{recordsError}</div>}
            {!recordsLoading && !error && !recordsError && (
              <div className="sales-visit-table-wrap debt-compact-table">
                <table className="leave-table">
                  <thead><tr><th>Client / Business</th><th>Actions</th><th>Loan balance</th><th>Status</th></tr></thead>
                  <tbody>
                    {records.length === 0
                      ? <tr><td colSpan="4">{canManage ? 'No debt collection records available.' : 'No accounts are currently assigned to you.'}</td></tr>
                      : records.map((item) => (
                        <React.Fragment key={item.id}>
                          <tr data-loan-id={item.id} className={item.is_duplicate ? 'debt-duplicate-row' : undefined}>
                            <td><strong>{item.agent_name}</strong><small>{item.business_name} · {item.business_location || 'Location not set'}</small><a className="debt-client-phone" href={`tel:${item.agent_number}`}>{item.agent_number}</a></td>
                            <td className="debt-action-cell">
                              {canManage && <button type="button" className="leave-primary-button debt-log-call" onClick={() => setLogInteractionLoan(item)}>Log Call</button>}
                              <button type="button" className="leave-text-button" aria-expanded={openCalls === item.id} onClick={() => toggleCalls(item.id)}>{openCalls === item.id ? 'Hide history' : 'View history'}</button>
                              {canPermanentlyDelete && <button type="button" className="leave-text-button debt-permanent-delete-button" onClick={() => permanentlyDeleteLoanRecord(item)}>Delete permanently</button>}
                              {canPermanentlyDelete && <button type="button" className="leave-text-button debt-permanent-delete-button" onClick={() => permanentlyDeleteClient(item)}>Delete client</button>}
                            </td>
                            <td><strong>{formatMoney(item.loan_balance)}</strong></td>
                            <td><span className="sales-outcome">{statusLabels[item.status] || item.status}</span></td>
                          </tr>
                          {openCalls === item.id && (
                            <tr className="debt-compact-history-row">
                              <td colSpan="4">
                                <section className="debt-call-history debt-compact-history" aria-label={`Interaction history for ${item.agent_name}`}>
                                  <strong>Interaction history · {item.agent_name}</strong>
                                  <DebtEntryDetails record={item} />
                                  {loadingCallLogs[item.id]
                                    ? <p className="leave-empty" role="status">Loading interaction history…</p>
                                    : (callLogs[item.id] || []).map((call) => (
                                        <article key={call.id}>
                                          <strong>{outcomes.find(([value]) => value === call.outcome)?.[1] || call.outcome}</strong>
                                          <span>Collector: {call.collector_name} · Contacted: {new Date(call.created_at).toLocaleString()}</span>
                                          <span>Debtor: {call.debtor_name || item.agent_name} · {call.business_name || item.business_name}</span>
                                          <span>Response: {outcomes.find(([value]) => value === call.outcome)?.[1] || call.outcome}</span>
                                          {call.notes && <p>Remarks: {call.notes}</p>}
                                          {call.promised_date && <span>Next payment: {new Date(`${call.promised_date}T${call.promised_time || '00:00'}`).toLocaleString()}{call.promised_amount ? ` · Agreed amount: ${formatMoney(call.promised_amount)}` : ''}</span>}
                                          {call.callback_date && <span>Callback: {new Date(`${call.callback_date}T${call.callback_time || '00:00'}`).toLocaleString()}</span>}
                                          <span>Paid to date: {formatMoney(call.amount_paid_to_date)} · Outstanding: {formatMoney(call.loan_balance)}</span>
                                          {Number(call.amount_paid) > 0 && <span>Payment on this call: {formatMoney(call.amount_paid)}</span>}
                                        </article>
                                      ))}
                                </section>
                              </td>
                            </tr>
                          )}
                        </React.Fragment>
                      ))}
                  </tbody>
                </table>
              </div>
            )}
        </>
        {logInteractionLoan && (
          <LogInteractionModal
            loan={logInteractionLoan}
            onClose={() => setLogInteractionLoan(null)}
            onSave={(payload) => saveInteraction(logInteractionLoan.id, payload)}
          />
        )}
      </section>
    );
  }

  return (
    <section className={`sales-reports-page debt-collection-page${compact ? ' debt-collection-page-compact' : ''}`} id="debt-collection">
      <div className="sales-page-hero">
        <div>
          <p className="leave-kicker">{canManage ? 'PORTFOLIO MANAGEMENT' : isGeneralManagerView ? 'GENERAL MANAGER · DEPARTMENT REPORT' : canViewAll ? 'ADMIN · DEPARTMENT REPORT' : canViewTeam ? 'ALL PORTFOLIO DEBTORS · READ ONLY' : 'COLLECTOR WORKSPACE'}</p>
          <h2>{canManage || canViewAll || canViewTeam ? 'Debt Collection' : 'My Assigned Portfolio'}</h2>
          <p className="leave-muted">{canManage ? 'Allocate accounts, monitor recovery, and manage outstanding balances.' : canViewTeam ? 'Browse every debtor in the debt-collection portfolio. Your summary and follow-ups remain limited to your team.' : canViewAll ? 'Read-only department-wide portfolio, recovery, and follow-up activity.' : 'Work your allocated accounts and record every client interaction.'}</p>
        </div>
      </div>

      {canViewAllDebtors && canViewTeam && !canViewAll && (
        <section className="debt-scope-notice" aria-label="All debtor list information">
          <div>
            <strong>All portfolio debtors</strong>
            <p>Select the checkboxes beside entries, then choose <b>View selected</b> to review one or more records together. This dashboard is read-only.</p>
          </div>
          <span>{recordsLoading ? 'Loading debtor list…' : `${listedDebtorCount} debtors · ${records.length} loan entries`}</span>
        </section>
      )}

      {canManage && (
        <section className="debt-import-toolbar" aria-label="Import debtor list">
          <div>
            <p className="leave-kicker">PORTFOLIO CONTROLS</p>
            <h3>Import debtor list</h3>
            <p className="leave-muted">Select the supplied Excel (.xlsx) or CSV file.</p>
          </div>
          <div className="debt-dashboard-transfer-actions">
            <input ref={importInput} className="debt-hidden-file-input" type="file" accept=".csv,.xlsx" onChange={chooseImportFile} aria-label="Choose debt collection CSV or Excel file" />
            <div className="debt-import-form">
              <button className="leave-secondary-button" type="button" onClick={() => importInput.current?.click()} disabled={importing}>Choose CSV / Excel</button>
              <button className="leave-primary-button" type="button" onClick={handleImportAction} disabled={importing}>{importing ? 'Importing…' : importFile ? 'Import portfolio' : 'Choose file to import'}</button>
              <button className="leave-secondary-button" type="button" onClick={downloadDebtCollectionTemplate}>Download CSV template</button>
            </div>
            {!compact && <div className="debt-export-actions">
              <button type="button" className="leave-secondary-button" onClick={() => downloadPortfolio('csv')}>Export CSV</button>
              <button type="button" className="leave-secondary-button" onClick={() => downloadPortfolio('xlsx')}>Export Excel</button>
            </div>}
          </div>
        </section>
      )}
      {canManage && <DebtCollectionImportStatus fileName={importFile?.name} status={importStatus} progress={importProgress} message={importFeedback} issues={importIssues} />}

      {loading && <p className="leave-empty" role="status">Loading debt collection portfolio summary…</p>}
      {recordsLoading && <p className="leave-empty" role="status">Loading debt collection accounts…</p>}
      {error && <div className="leave-alert error" role="status">{error}</div>}
      {recordsError && <div className="leave-alert error" role="alert">{recordsError}</div>}
      {supplementalError && <div className="leave-alert error" role="alert">{supplementalError}</div>}
      {message && <div className={`leave-alert ${messageType === 'error' ? 'error' : 'info'}`} role={messageType === 'error' ? 'alert' : 'status'}>{message}</div>}

      {!loading && !error && (
        <>
          {canViewAll || canViewTeam ? (
            <div className="report-card-grid">
              <div className="report-card"><span>{canViewTeam && !canViewAll ? 'Team outstanding' : isGeneralManagerView ? 'Department outstanding' : 'Total outstanding'}</span><strong>{formatMoney(summary.total_outstanding)}</strong></div>
              <div className="report-card"><span>Active accounts</span><strong>{summary.active_accounts || 0}</strong></div>
              <div className="report-card"><span>Overdue accounts</span><strong>{summary.overdue_accounts || 0}</strong></div>
              <div className="report-card"><span>Recovered to date</span><strong>{formatMoney(summary.recovered_to_date)}</strong></div>
            </div>
          ) : (
            <div className="report-card-grid">
              <div className="report-card"><span>My total outstanding</span><strong>{formatMoney(summary.total_outstanding)}</strong></div>
              <div className="report-card"><span>Promises to pay today</span><strong>{performance?.periods?.daily?.promises_to_pay || 0}</strong></div>
              <div className="report-card"><span>Recovered today</span><strong>{formatMoney(performance?.periods?.daily?.recovered)}</strong></div>
            </div>
          )}

          {(canViewAll || canViewTeam) && (
            <section className={`debt-daily-reports${compact ? ' is-compact' : ''}`}>
              {compact && (
                <button
                  type="button"
                  className="debt-daily-reports-toggle"
                  aria-expanded={dailyReportsExpanded}
                  onClick={() => setDailyReportsExpanded((expanded) => !expanded)}
                >
                  <span>{canViewTeam && !canViewAll ? 'Team interactions' : isGeneralManagerView ? 'Department interactions' : 'Daily call reports'}</span>
                  <span>{analytics?.interactions?.length || 0} interactions</span>
                  <span aria-hidden="true">{dailyReportsExpanded ? '−' : '+'}</span>
                </button>
              )}
              {(!compact || dailyReportsExpanded) && (
                <CollectorInteractionTable
                  interactions={analytics?.interactions || []}
                  loading={analyticsLoading}
                  onOpenLoan={openLoanFromReport}
                  onImportClick={canManage ? handleImportAction : undefined}
                  importReady={Boolean(importFile)}
                  importing={importing}
                />
              )}
            </section>
          )}

          {canManage && !compact ? (
            <>
              <section className="leave-section debt-manager-tools">
                <div className="leave-section-heading"><div><p className="leave-kicker">PORTFOLIO CONTROLS</p><h3>Debtor management</h3></div></div>
                <form className="debt-form-grid" onSubmit={submitDebtor}>
                  <div className="debt-form-actions"><ClientProfileLookup onConfirm={confirmClientProfile} /></div>
                  <label>First name<input value={debtor.first_name} onChange={setDebtorField('first_name')} required /></label>
                  <label>Middle and last names<input value={debtor.other_names} onChange={setDebtorField('other_names')} /></label>
                  <label>Agent phone<input value={debtor.agent_msisdn} onChange={setDebtorField('agent_msisdn')} required /></label>
                  <label>Business owner phone<input value={debtor.owner_msisdn} onChange={setDebtorField('owner_msisdn')} /></label>
                  <label>Business operator phone<input value={debtor.operator_msisdn} onChange={setDebtorField('operator_msisdn')} /></label>
                  <label>Unique agent ID<input value={debtor.agent_no} onChange={setDebtorField('agent_no')} required /></label>
                  <label>Store number<input value={debtor.store_number} onChange={setDebtorField('store_number')} /></label>
                  <label>Registered business name<input value={debtor.business_name} onChange={setDebtorField('business_name')} required /></label>
                  <label>Physical location<input value={debtor.location} onChange={setDebtorField('location')} /></label>
                  <label>Original loan amount<input type="number" min="0.01" step="0.01" value={loan.loan_amount} onChange={(event) => setLoan({ ...loan, loan_amount: event.target.value })} /></label>
                  <label>Disbursement date<input type="date" value={loan.loan_date} onChange={(event) => setLoan({ ...loan, loan_date: event.target.value })} /></label>
                  <label>Amount already paid<input type="number" min="0" step="0.01" value={loan.amount_paid} onChange={(event) => setLoan({ ...loan, amount_paid: event.target.value })} /></label>
                  <label>Last interest calculation<input type="date" value={loan.last_interest_calc_date} onChange={(event) => setLoan({ ...loan, last_interest_calc_date: event.target.value })} /></label>
                  <label>Days since disbursement<input type="number" min="0" step="1" value={loan.no_of_days} onChange={(event) => setLoan({ ...loan, no_of_days: event.target.value })} /></label>
                  <label>Loan status<select value={loan.status} onChange={(event) => setLoan({ ...loan, status: event.target.value })}>{Object.entries(statusLabels).filter(([value]) => value !== 'written_off').map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label>
                  <div className="debt-form-actions"><button className="leave-primary-button" type="submit">Save debtor / loan</button></div>
                </form>
              </section>

              {analytics && <section className="leave-section debt-analytics">
                <div className="leave-section-heading"><div><p className="leave-kicker">RECOVERY MONITOR</p><h3>Portfolio health and collector performance</h3></div></div>
                <form className="debt-analytics-filter" onSubmit={filterAnalytics}><label>From<input type="date" value={analyticsDates.from} onChange={(event) => setAnalyticsDates({ ...analyticsDates, from: event.target.value })} /></label><label>To<input type="date" value={analyticsDates.to} onChange={(event) => setAnalyticsDates({ ...analyticsDates, to: event.target.value })} /></label><label>Representative<select value={analyticsCollectorId} onChange={(event) => setAnalyticsCollectorId(event.target.value)}><option value="">All representatives</option>{collectors.map((collector) => <option key={collector.id} value={collector.id}>{collector.full_name}</option>)}</select></label><button className="leave-secondary-button" type="submit">Filter reports</button></form>
                <div className="report-card-grid"><div className="report-card"><span>Book accounts</span><strong>{analytics.portfolio.accounts}</strong></div><div className="report-card"><span>Current outstanding</span><strong>{formatMoney(analytics.portfolio.outstanding)}</strong></div><div className="report-card"><span>Period recovered</span><strong>{formatMoney(analytics.period_recovered)}</strong></div><div className="report-card"><span>Period calls</span><strong>{analytics.period_calls}</strong></div></div>
                <div className="debt-recovery-trends" aria-label="Daily recovery trend">
                  <strong>Recovery trends</strong>
                  {analytics.recovery_trends?.length ? analytics.recovery_trends.map((trend) => {
                    const maximum = Math.max(...analytics.recovery_trends.map((item) => Number(item.recovered)));
                    const width = maximum ? Math.max(3, (Number(trend.recovered) / maximum) * 100) : 3;
                    return <div className="debt-recovery-trend" key={trend.date}><time>{trend.date}</time><span><i style={{ width: `${width}%` }} /></span><strong>{formatMoney(trend.recovered)}</strong></div>;
                  }) : <p className="leave-empty">No recovery payments in this date range.</p>}
                </div>
                <div className="sales-visit-table-wrap"><table className="leave-table"><thead><tr><th>Collector</th><th>Assigned</th><th>Contacted</th><th>Pending</th><th>Calls</th><th>Payments</th><th>Recovered</th></tr></thead><tbody>{analytics.collectors.length ? analytics.collectors.map((item) => <tr key={item.collector_id}><td>{item.collector_name}</td><td>{item.assigned_accounts}</td><td>{item.contacted_accounts}</td><td>{item.pending_accounts}</td><td>{item.calls}</td><td>{item.payments}</td><td>{formatMoney(item.recovered)}</td></tr>) : <tr><td colSpan="7">No collector activity in this period.</td></tr>}</tbody></table></div>
              </section>}

            </>
          ) : (
            null
          )}

          {canManage && <div className="leave-section-heading debt-portfolio-heading"><div><p className="leave-kicker">{archiveView ? 'ARCHIVED RECORDS' : 'MASTER DEBTOR LIST'}</p><h3>{archiveView ? 'Archived accounts' : 'Portfolio accounts'}</h3><p className="leave-muted">{archiveView ? 'Archived accounts are retained and can be restored.' : 'Filter, review, update, and allocate the full outstanding portfolio.'}</p></div><div className="debt-record-view-toggle" role="group" aria-label="Portfolio record view"><button type="button" aria-pressed={!archiveView} className={!archiveView ? 'active' : ''} onClick={() => { setArchiveView(false); setSelectedLoans([]); }}>Active portfolio</button><button type="button" aria-pressed={archiveView} className={archiveView ? 'active' : ''} onClick={() => { setArchiveView(true); setSelectedLoans([]); }}>Archive</button></div></div>}
          {canSelectLoans && selectedLoans.length > 0 && (
            <div className="debt-portfolio-sticky-controls">
              <div className="debt-assignment-bar" aria-label="Selected record actions">
                <strong aria-live="polite">{selectedLoans.length} selected</strong>
                <button type="button" className="leave-secondary-button debt-selected-view-button" onClick={() => selectedLoans.length === 1 ? openSelectedRecord('view') : setMultiViewOpen(true)} disabled={!selectedRecords.length} title={selectedLoans.length === 1 ? 'View selected record' : 'View all selected records'}>View selected</button>
                {canEditRecords && <button type="button" className="leave-secondary-button debt-selected-edit-button" onClick={() => openSelectedRecord('edit')} disabled={selectedLoans.length !== 1 || !selectedRecord || archiveView} title={selectedLoans.length === 1 ? 'Edit selected record' : 'Select one record to edit its details'}>Edit</button>}
                {canManage && !archiveView && <button type="button" className="leave-primary-button" onClick={() => setDistributionOpen(true)} disabled={archiving}>Distribute List</button>}
                {canManage && (archiveView
                  ? <button type="button" className="leave-secondary-button" onClick={restoreSelectedLoans} disabled={archiving}>Restore selected</button>
                  : <button type="button" className="leave-secondary-button debt-archive-button" onClick={archiveSelectedLoans} disabled={archiving}>Archive selected</button>)}
                {canPermanentlyDelete && <button type="button" className="leave-secondary-button debt-permanent-delete-button" onClick={permanentlyDeleteSelectedLoans} disabled={archiving}>Delete selected permanently</button>}
                {selectedLoans.length > 1 && <span className="debt-selection-hint">{canEditRecords ? 'View all selected records; edit one record at a time.' : 'View all selected records at once.'}</span>}
              </div>
            </div>
          )}

          <form className="debt-filter-bar" onSubmit={applyFilters}>
            <label>Search<input value={filters.q} onChange={(event) => setFilters({ ...filters, q: event.target.value })} placeholder="Agent ID or collector name / number" /></label>
            <label>Status<select value={filters.status} onChange={(event) => setFilters({ ...filters, status: event.target.value })}><option value="">All statuses</option>{Object.entries(statusLabels).map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label>
            {canManage && <><label>Agent name<input value={filters.agent_name} onChange={(event) => setFilters({ ...filters, agent_name: event.target.value })} /></label><label>Agent phone / number<input value={filters.agent_number} onChange={(event) => setFilters({ ...filters, agent_number: event.target.value })} /></label><label>Business name<input value={filters.business_name} onChange={(event) => setFilters({ ...filters, business_name: event.target.value })} /></label><label>Location<input value={filters.location} onChange={(event) => setFilters({ ...filters, location: event.target.value })} /></label><label>Store number<input value={filters.store_number} onChange={(event) => setFilters({ ...filters, store_number: event.target.value })} /></label><label>Collector<select value={filters.collector_id} onChange={(event) => setFilters({ ...filters, collector_id: event.target.value })}><option value="">All collectors</option>{collectors.map((collector) => <option key={collector.id} value={collector.id}>{collector.full_name} ({collector.active_accounts} active)</option>)}</select></label><label>Max collector load<input type="number" min="0" step="1" value={filters.collector_capacity} onChange={(event) => setFilters({ ...filters, collector_capacity: event.target.value })} placeholder="Active accounts" /></label><label>Minimum balance<input type="number" min="0" step="0.01" value={filters.min_balance} onChange={(event) => setFilters({ ...filters, min_balance: event.target.value })} /></label><label>Maximum balance<input type="number" min="0" step="0.01" value={filters.max_balance} onChange={(event) => setFilters({ ...filters, max_balance: event.target.value })} /></label><label>Overdue age (days)<input type="number" min="0" step="1" value={filters.overdue_days} onChange={(event) => setFilters({ ...filters, overdue_days: event.target.value })} /></label></>}
            <button type="submit" className="leave-secondary-button">Apply filters</button>
            <button type="button" className="leave-text-button" onClick={() => { const cleared = { q: '', agent_name: '', agent_number: '', business_name: '', status: '', location: '', store_number: '', min_balance: '', max_balance: '', overdue_days: '', collector_id: '', collector_capacity: '' }; setFilters(cleared); setAppliedFilters(''); }}>Clear</button>
          </form>

          <div className="sales-visit-table-wrap debt-portfolio-table-wrap">
            <table className="leave-table debt-portfolio-table">
              <colgroup>
                {canSelectLoans && <col style={{ width: '3%' }} />}
                <col style={{ width: '19%' }} />
                <col style={{ width: '7%' }} />
                <col style={{ width: '8%' }} />
                <col style={{ width: '7%' }} />
                <col style={{ width: '9%' }} />
                <col style={{ width: '8%' }} />
                <col style={{ width: '10%' }} />
                <col style={{ width: '10%' }} />
                <col style={{ width: '8%' }} />
                <col style={{ width: canSelectLoans ? '11%' : '14%' }} />
              </colgroup>
              <thead>
                <tr>
                  {canSelectLoans && <th className="debt-selection-cell"><label className="debt-checkbox-target" title="Select all visible entries"><input aria-label="Select all loans" type="checkbox" checked={records.length > 0 && records.every((item) => selectedLoans.includes(item.id))} onChange={(event) => setSelectedLoans((current) => event.target.checked ? Array.from(new Set([...current, ...records.map((item) => item.id)])) : current.filter((id) => !records.some((item) => item.id === id)))} /></label></th>}
                  <th aria-sort={portfolioAriaSort('agent_name')}>{portfolioSortHeader('Debtor / business', 'agent_name')}</th>
                  <th aria-sort={portfolioAriaSort('store_number')}>{portfolioSortHeader('Store number', 'store_number')}</th>
                  <th aria-sort={portfolioAriaSort('loan_amount')}>{portfolioSortHeader('Original loan', 'loan_amount')}</th>
                  <th aria-sort={portfolioAriaSort('amount_paid')}>{portfolioSortHeader('Paid', 'amount_paid')}</th>
                  <th aria-sort={portfolioAriaSort('loan_balance')}>{portfolioSortHeader('Balance', 'loan_balance')}</th>
                  <th aria-sort={portfolioAriaSort('status')}>{portfolioSortHeader('Status', 'status')}</th>
                  <th aria-sort={portfolioAriaSort('collector_name')}>{portfolioSortHeader('Collector', 'collector_name')}</th>
                  <th aria-sort={portfolioAriaSort('next_payment_date')}>{portfolioSortHeader('Next payment', 'next_payment_date')}</th>
                  <th aria-sort={portfolioAriaSort('last_contact')}>{portfolioSortHeader('Last contact', 'last_contact')}</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {recordsLoading ? (
                  <tr><td colSpan={canSelectLoans ? 11 : 10}>Loading accounts…</td></tr>
                ) : recordsError ? (
                  <tr><td colSpan={canSelectLoans ? 11 : 10}>Accounts could not be loaded.</td></tr>
                ) : records.length === 0 ? (
                  <tr><td colSpan={canSelectLoans ? 11 : 10}>No debt collection records available.</td></tr>
                ) : sortedRecords.map((item) => (
                  <React.Fragment key={item.id}>
                    <tr data-loan-id={item.id}>
                      {canSelectLoans && <td className="debt-selection-cell"><label className="debt-checkbox-target" title={`Select ${item.agent_name}`}><input aria-label={`Select ${item.agent_name}`} type="checkbox" checked={selectedLoans.includes(item.id)} onChange={(event) => setSelectedLoans((current) => event.target.checked ? [...current, item.id] : current.filter((id) => id !== item.id))} /></label></td>}
                      <td className="debt-portfolio-identity">
                        <strong>{item.agent_name || 'Name unavailable'}{item.is_duplicate && <span className="debt-duplicate-badge">Duplicate</span>}</strong>
                        <small>{item.business_name || 'Business not provided'}</small>
                        {item.agent_number ? <a className="debt-client-phone" href={`tel:${item.agent_number}`}>{item.agent_number}</a> : <small>No phone recorded</small>}
                      </td>
                      <td>{item.store_number || '-'}</td>
                      <td>{formatMoney(item.loan_amount)}</td>
                      <td>{formatMoney(item.amount_paid)}</td>
                      <td className="debt-compact-balance"><strong>{formatMoney(item.loan_balance)}</strong></td>
                      <td><span className="sales-outcome">{statusLabels[item.status] || item.status || 'Unknown'}</span></td>
                      <td className="debt-assigned-to" title={item.collector_name || 'Unassigned'}>{item.collector_name || 'Unassigned'}</td>
                      <td className="debt-next-payment">{item.next_payment_date ? <><strong>{formatTableDate(item.next_payment_date)} {item.next_payment_time || ''}</strong>{item.next_payment_amount ? <small>{formatMoney(item.next_payment_amount)}</small> : null}</> : 'No promise'}</td>
                      <td className="debt-last-contact" title={item.last_contact || 'No contact recorded'}>{item.last_contact ? formatTableDate(item.last_contact) : 'No contact'}</td>
                      <td className="debt-action-cell debt-portfolio-actions">
                        <button type="button" className="leave-secondary-button debt-view-activity-button" onClick={() => toggleCalls(item.id)}>View</button>
                        {!archiveView && canManage && <button type="button" className="leave-primary-button debt-log-call" onClick={() => setLogInteractionLoan(item)}>Log call</button>}
                        {!archiveView && canEditRecords && <button type="button" className="leave-secondary-button debt-edit-row-button" onClick={() => {
                          setSelectedLoans([item.id]);
                          openSelectedRecord('edit', item);
                        }}>Edit</button>}
                        {!archiveView && canManage && <button type="button" className="leave-text-button debt-delete-row-button" onClick={() => deleteLoanRecord(item)}>Delete</button>}
                        {!archiveView && canManage && item.is_duplicate && !canPermanentlyDelete && <button type="button" className="leave-text-button debt-permanent-delete-button" onClick={() => permanentlyDeleteLoanRecord(item)}>Delete duplicate permanently</button>}
                        {!archiveView && canPermanentlyDelete && <button type="button" className="leave-text-button debt-permanent-delete-button" onClick={() => permanentlyDeleteLoanRecord(item)}>Delete permanently</button>}
                        {!archiveView && canPermanentlyDelete && <button type="button" className="leave-text-button debt-permanent-delete-button" onClick={() => permanentlyDeleteClient(item)}>Delete client</button>}
                        {archiveView && canManage && <button type="button" className="leave-text-button debt-restore-row-button" onClick={() => restoreLoan(item)} disabled={archiving}>Restore</button>}
                      </td>
                    </tr>
                    {openCalls === item.id && createPortal(
                      <div className="debt-modal-backdrop debt-activity-backdrop" role="presentation" onMouseDown={(event) => {
                        if (event.target === event.currentTarget) setOpenCalls(null);
                      }}>
                        <section className="debt-interaction-modal debt-activity-modal" role="dialog" aria-modal="true" aria-labelledby="debt-activity-title">
                          <div className="debt-modal-heading">
                            <div>
                              <p className="leave-kicker">ACCOUNT ACTIVITY</p>
                              <h2 id="debt-activity-title">{item.agent_name} · {item.business_name}</h2>
                            </div>
                            {!archiveView && canEditRecords && <button type="button" className="leave-secondary-button debt-selected-edit-button" onClick={() => {
                              setSelectedLoans([item.id]);
                              setOpenCalls(null);
                              openSelectedRecord('edit', item);
                            }}>Edit entry</button>}
                            <button type="button" className="debt-modal-close" aria-label="Close activity" onClick={() => setOpenCalls(null)}>×</button>
                          </div>
                          <div className="debt-activity-panel">
                        <DebtEntryDetails record={item} />
                        {canEditRecords && <div className="debt-record-editors">
                          <form onSubmit={(event) => saveDebtorDetails(event, item)}><strong>Edit debtor</strong><label>First name<input required value={(debtorEdits[item.debtor_id] || item).first_name || ''} onChange={(event) => updateDebtorEdit(item, 'first_name', event.target.value)} /></label><label>Other names<input value={(debtorEdits[item.debtor_id] || item).other_names || ''} onChange={(event) => updateDebtorEdit(item, 'other_names', event.target.value)} /></label><label>Agent phone<input required value={(debtorEdits[item.debtor_id] || item).agent_number || ''} onChange={(event) => updateDebtorEdit(item, 'agent_number', event.target.value)} /></label><label>Owner phone<input value={(debtorEdits[item.debtor_id] || item).owner_msisdn || ''} onChange={(event) => updateDebtorEdit(item, 'owner_msisdn', event.target.value)} /></label><label>Operator phone<input value={(debtorEdits[item.debtor_id] || item).operator_msisdn || ''} onChange={(event) => updateDebtorEdit(item, 'operator_msisdn', event.target.value)} /></label><label>Agent identifier<input required value={(debtorEdits[item.debtor_id] || item).agent_no || ''} onChange={(event) => updateDebtorEdit(item, 'agent_no', event.target.value)} /></label><label>Store number<input value={(debtorEdits[item.debtor_id] || item).store_number || ''} onChange={(event) => updateDebtorEdit(item, 'store_number', event.target.value)} /></label><label>Business name<input required value={(debtorEdits[item.debtor_id] || item).business_name || ''} onChange={(event) => updateDebtorEdit(item, 'business_name', event.target.value)} /></label><label>Location<input value={(debtorEdits[item.debtor_id] || item).business_location || ''} onChange={(event) => updateDebtorEdit(item, 'business_location', event.target.value)} /></label><div className="debt-edit-action"><button className="leave-secondary-button" type="submit">Save debtor</button></div></form>
                          <form onSubmit={(event) => saveLoanDetails(event, item)}><strong>Edit loan terms</strong><label>Original loan amount<input type="number" min="0.01" step="0.01" required value={loanEdits[item.id]?.loan_amount ?? item.loan_amount} onChange={(event) => setLoanEdits((current) => ({ ...current, [item.id]: { ...current[item.id], loan_amount: event.target.value } }))} /></label><label>Disbursed date<input type="date" required value={loanEdits[item.id]?.loan_date ?? item.loan_date} onChange={(event) => setLoanEdits((current) => ({ ...current, [item.id]: { ...current[item.id], loan_date: event.target.value } }))} /></label><label>Last interest calculation<input type="date" value={loanEdits[item.id]?.last_interest_calc_date ?? item.last_interest_calc_date ?? ''} onChange={(event) => setLoanEdits((current) => ({ ...current, [item.id]: { ...current[item.id], last_interest_calc_date: event.target.value || null } }))} /></label><label>Loan status<select value={loanEdits[item.id]?.status ?? item.status} onChange={(event) => setLoanEdits((current) => ({ ...current, [item.id]: { ...current[item.id], status: event.target.value } }))}>{Object.entries(statusLabels).filter(([value]) => value !== 'written_off').map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label><div className="debt-edit-action"><button className="leave-secondary-button" type="submit">Save loan</button></div></form>
                        </div>}
                        {canManage && <form className="debt-call-form" onSubmit={(event) => submitCall(event, item.id)}>
                          <label>Call outcome<select required value={callDrafts[item.id]?.outcome || ''} onChange={(event) => updateCallDraft(item.id, 'outcome', event.target.value)}><option value="">Select outcome</option>{outcomes.map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label>
                          {callDrafts[item.id]?.outcome === 'promise_to_pay' && <><label>Promise date<input type="date" required value={callDrafts[item.id]?.promised_date || ''} onChange={(event) => updateCallDraft(item.id, 'promised_date', event.target.value)} /></label><label>Promise time<input type="time" required value={callDrafts[item.id]?.promised_time || ''} onChange={(event) => updateCallDraft(item.id, 'promised_time', event.target.value)} /></label><label>Promised amount<input type="number" min="0" step="0.01" value={callDrafts[item.id]?.promised_amount || ''} onChange={(event) => updateCallDraft(item.id, 'promised_amount', event.target.value)} /></label></>}
                          {callDrafts[item.id]?.outcome === 'callback_requested' && <><label>Callback date<input type="date" required value={callDrafts[item.id]?.callback_date || ''} onChange={(event) => updateCallDraft(item.id, 'callback_date', event.target.value)} /></label><label>Callback time<input type="time" required value={callDrafts[item.id]?.callback_time || ''} onChange={(event) => updateCallDraft(item.id, 'callback_time', event.target.value)} /></label></>}
                          {callDrafts[item.id]?.outcome === 'partial_payment' && <><label>Amount paid<input type="number" min="0.01" step="0.01" required value={callDrafts[item.id]?.amount_paid || ''} onChange={(event) => updateCallDraft(item.id, 'amount_paid', event.target.value)} /></label><label>Next payment date<input type="date" required value={callDrafts[item.id]?.promised_date || ''} onChange={(event) => updateCallDraft(item.id, 'promised_date', event.target.value)} /></label><label>Next payment time<input type="time" required value={callDrafts[item.id]?.promised_time || ''} onChange={(event) => updateCallDraft(item.id, 'promised_time', event.target.value)} /></label><label>Agreed next payment amount<input type="number" min="0.01" step="0.01" value={callDrafts[item.id]?.promised_amount || ''} onChange={(event) => updateCallDraft(item.id, 'promised_amount', event.target.value)} /></label></>}
                          <label className="debt-notes-field">Interaction notes<textarea rows="2" value={callDrafts[item.id]?.notes || ''} onChange={(event) => updateCallDraft(item.id, 'notes', event.target.value)} /></label>
                          <button className="leave-primary-button" type="submit">Save interaction</button>
                        </form>}
                        {canManage && <div className="debt-manager-actions">
                          <form onSubmit={(event) => submitRating(event, item.id)}><strong>Approve credit rating</strong><select aria-label="Credit grade" value={ratingDrafts[item.id]?.grade || 'C'} onChange={(event) => setRatingDrafts((current) => ({ ...current, [item.id]: { ...current[item.id], grade: event.target.value } }))}>{['A', 'B', 'C', 'D', 'E'].map((grade) => <option key={grade}>{grade}</option>)}</select><input aria-label="Credit score" type="number" min="0" max="100" value={ratingDrafts[item.id]?.score || '50'} onChange={(event) => setRatingDrafts((current) => ({ ...current, [item.id]: { ...current[item.id], score: event.target.value } }))} /><input aria-label="Rating reason" placeholder="Reason for rating" required value={ratingDrafts[item.id]?.reason || ''} onChange={(event) => setRatingDrafts((current) => ({ ...current, [item.id]: { ...current[item.id], reason: event.target.value } }))} /><button className="leave-secondary-button" type="submit">Approve rating</button></form>
                          <form onSubmit={(event) => approveWriteOff(event, item.id)}><strong>Approve loan write-off</strong><input required aria-label="Write-off reason" placeholder="Reason required" value={writeOffReasons[item.id] || ''} onChange={(event) => setWriteOffReasons((current) => ({ ...current, [item.id]: event.target.value }))} /><button className="leave-secondary-button" type="submit">Approve write-off</button></form>
                        </div>}
                        <div className="debt-call-history"><strong>Interaction history · {item.agent_name} · {item.business_name}</strong>{loadingCallLogs[item.id] ? <p className="leave-empty">Loading call log…</p> : (callLogs[item.id] || []).map((call) => <article key={call.id}><strong>{outcomes.find(([value]) => value === call.outcome)?.[1] || call.outcome}</strong><span>Collector: {call.collector_name} · Contacted: {new Date(call.created_at).toLocaleString()}</span><span>Debtor: {call.debtor_name || item.agent_name} · {call.business_name || item.business_name}</span><span>Response: {outcomes.find(([value]) => value === call.outcome)?.[1] || call.outcome}</span>{call.notes && <p>Remarks: {call.notes}</p>}{call.promised_date && <span>Promise: {call.promised_date} {call.promised_time || ''}{call.promised_amount ? ` · ${formatMoney(call.promised_amount)}` : ''}</span>}{call.callback_date && <span>Callback: {call.callback_date} {call.callback_time || ''}</span>}{Number(call.amount_paid) > 0 && <span>Payment: {formatMoney(call.amount_paid)} · Paid to date: {formatMoney(call.amount_paid_to_date)} · Balance: {formatMoney(call.loan_balance)}</span>}</article>)}</div>
                          </div>
                        </section>
                      </div>,
                      document.body,
                    )}
                  </React.Fragment>
                ))}
              </tbody>
            </table>
          </div>

          {canManage && compact && (
            <CollectorInteractionTable
              interactions={analytics?.interactions || []}
              loading={analyticsLoading}
              onOpenLoan={openLoanFromReport}
              onImportClick={handleImportAction}
              importReady={Boolean(importFile)}
              importing={importing}
            />
          )}

          {followUps.length > 0 && <section className="leave-section debt-follow-ups"><div className="leave-section-heading"><div><p className="leave-kicker">SCHEDULED ACTIONS</p><h3>{canViewTeam && !canViewAll ? 'Team follow-ups' : canViewAll ? 'Upcoming collector follow-ups' : 'My follow-up queue'}</h3></div></div><div className="sales-visit-table-wrap"><table className="leave-table"><thead><tr><th>Due</th><th>Type</th><th>Debtor</th><th>Business</th>{(canViewAll || canViewTeam) && <th>Collector</th>}<th>Status</th><th>Action</th></tr></thead><tbody>{followUps.map((item) => <tr key={item.id}><td>{new Date(item.due_at).toLocaleString()}</td><td>{item.follow_up_type}</td><td>{item.debtor.agent_name}</td><td>{item.debtor.business_name}</td>{(canViewAll || canViewTeam) && <td>{item.collector_name}</td>}<td>{item.status}</td><td>{item.status === 'Pending' && (!canManage ? 'Read-only' : <button type="button" className="leave-text-button" onClick={() => completeFollowUp(item.id)}>Mark complete</button>)}</td></tr>)}</tbody></table></div></section>}
        </>
      )}
      {logInteractionLoan && (
        <LogInteractionModal
          loan={logInteractionLoan}
          onClose={() => setLogInteractionLoan(null)}
          onSave={(payload) => saveInteraction(logInteractionLoan.id, payload)}
        />
      )}
      {distributionOpen && (
        <div className="debt-modal-backdrop" role="presentation" onMouseDown={(event) => {
          if (event.target === event.currentTarget) setDistributionOpen(false);
        }}>
          <section className="debt-interaction-modal" role="dialog" aria-modal="true" aria-labelledby="distribution-title">
            <div className="debt-modal-heading">
              <div><p className="leave-kicker">PORTFOLIO MANAGEMENT</p><h2 id="distribution-title">Distribute selected accounts</h2></div>
              <button type="button" className="leave-text-button" onClick={() => setDistributionOpen(false)}>Close</button>
            </div>
            <form className="debt-modal-form" onSubmit={assignSelected}>
              <label>Debt collector
                <select value={collectorId} onChange={(event) => setCollectorId(event.target.value)} required>
                  <option value="">Choose debt collector</option>
                  {allocationCollectors.map((collector) => <option key={collector.id} value={collector.id}>{collector.full_name} · {collector.active_accounts} active</option>)}
                </select>
              </label>
              {selectedHaveAssignments && <label>Reason for reassignment
                <textarea value={assignmentReason} onChange={(event) => setAssignmentReason(event.target.value)} maxLength="255" required />
              </label>}
              <p>{selectedLoans.length} loan{selectedLoans.length === 1 ? '' : 's'} will be assigned.</p>
              <div className="debt-modal-actions">
                <button type="button" className="leave-secondary-button" onClick={() => setDistributionOpen(false)}>Cancel</button>
                <button type="submit" className="leave-primary-button">Assign selected</button>
              </div>
            </form>
          </section>
        </div>
      )}
      {multiViewOpen && selectedRecords.length > 0 && (
        <div className="debt-modal-backdrop" role="presentation" onMouseDown={(event) => {
          if (event.target === event.currentTarget) setMultiViewOpen(false);
        }}>
          <section className="debt-interaction-modal debt-record-modal debt-multi-record-modal" role="dialog" aria-modal="true" aria-labelledby="debt-multi-view-title">
            <div className="debt-modal-heading">
              <div>
                <p className="leave-kicker">PORTFOLIO RECORDS</p>
                <h2 id="debt-multi-view-title">{selectedRecords.length} selected entries</h2>
                <p className="leave-muted">Review details for each selected account.</p>
              </div>
              <button type="button" className="debt-modal-close" aria-label="Close selected entries" onClick={() => setMultiViewOpen(false)}>×</button>
            </div>
            <div className="debt-multi-record-list">
              {selectedRecords.map((record) => (
                <article className="debt-multi-record" key={record.id}>
                  <div className="debt-multi-record-heading">
                    <h3>{record.agent_name} · {record.business_name}</h3>
                    {!archiveView && canEditRecords && <button type="button" className="leave-secondary-button debt-selected-edit-button" onClick={() => openSelectedRecord('edit', record)}>Edit / update entry</button>}
                  </div>
                  <DebtEntryDetails record={record} />
                </article>
              ))}
            </div>
          </section>
        </div>
      )}
      {recordPanel && selectedRecord && (
        <div className="debt-modal-backdrop" role="presentation" onMouseDown={(event) => {
          if (event.target === event.currentTarget) setRecordPanel(null);
        }}>
          <section
            className="debt-interaction-modal debt-record-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="debt-record-title"
          >
            <div className="debt-modal-heading">
              <div>
                <p className="leave-kicker">{recordPanel.mode === 'edit' ? 'UPDATE PORTFOLIO RECORD' : 'PORTFOLIO RECORD'}</p>
                <h2 id="debt-record-title">{recordPanel.mode === 'edit' ? 'Edit selected record' : 'Selected record details'}</h2>
                <p className="leave-muted">{recordPanel.mode === 'edit' ? 'Update client and loan details below.' : `${selectedRecord.agent_name} · ${selectedRecord.business_name}`}</p>
              </div>
              <div className="debt-modal-heading-actions">
                {recordPanel.mode === 'view' && canEditRecords && !archiveView && <button type="button" className="leave-secondary-button debt-selected-edit-button" onClick={() => openSelectedRecord('edit')}>Edit / update entry</button>}
                <button type="button" className="leave-text-button" onClick={() => setRecordPanel(null)}>Close</button>
              </div>
            </div>

            {recordFeedback && (
              <div className={`leave-alert ${recordFeedback.type}`} role={recordFeedback.type === 'error' ? 'alert' : 'status'}>
                {recordFeedback.text}
              </div>
            )}

            {recordPanel.mode === 'view' ? (
              <dl className="debt-record-detail-grid">
                <div><dt>Agent name</dt><dd>{selectedRecord.agent_name || '-'}</dd></div>
                <div><dt>First name</dt><dd>{selectedRecord.first_name || '-'}</dd></div>
                <div><dt>Other names</dt><dd>{selectedRecord.other_names || '-'}</dd></div>
                <div><dt>Agent phone</dt><dd>{selectedRecord.agent_number || '-'}</dd></div>
                <div><dt>Owner phone</dt><dd>{selectedRecord.owner_msisdn || '-'}</dd></div>
                <div><dt>Operator phone</dt><dd>{selectedRecord.operator_msisdn || '-'}</dd></div>
                <div><dt>Agent number</dt><dd>{selectedRecord.agent_no || '-'}</dd></div>
                <div><dt>Store number</dt><dd>{selectedRecord.store_number || '-'}</dd></div>
                <div><dt>Registered business</dt><dd>{selectedRecord.business_name || '-'}</dd></div>
                <div><dt>Location</dt><dd>{selectedRecord.business_location || '-'}</dd></div>
                <div><dt>Original loan</dt><dd>{formatMoney(selectedRecord.loan_amount)}</dd></div>
                <div><dt>Paid to date</dt><dd>{formatMoney(selectedRecord.amount_paid)}</dd></div>
                <div><dt>Outstanding balance</dt><dd>{formatMoney(selectedRecord.loan_balance)}</dd></div>
                <div><dt>Last interest calculation</dt><dd>{selectedRecord.last_interest_calc_date || '-'}</dd></div>
                <div><dt>Disbursed</dt><dd>{selectedRecord.loan_date || '-'}</dd></div>
                <div><dt>Days since issue</dt><dd>{selectedRecord.no_of_days ?? '-'}</dd></div>
                <div><dt>Loans borrowed</dt><dd>{selectedRecord.loans_borrowed ?? '-'}</dd></div>
                <div><dt>Next agreed payment</dt><dd>{selectedRecord.next_payment_date ? `${selectedRecord.next_payment_date} ${selectedRecord.next_payment_time || ''}${selectedRecord.next_payment_amount ? ` · ${formatMoney(selectedRecord.next_payment_amount)}` : ''}` : '-'}</dd></div>
                <div><dt>Status</dt><dd>{statusLabels[selectedRecord.status] || selectedRecord.status}</dd></div>
                <div><dt>Credit rating</dt><dd>{selectedRecord.credit_rating ? `${selectedRecord.credit_rating} · ${selectedRecord.credit_score}` : '-'}</dd></div>
                <div><dt>Collector</dt><dd>{selectedRecord.collector_name || 'Unassigned'}</dd></div>
                <div><dt>Assignment reason</dt><dd>{selectedRecord.assignment_reason || '-'}</dd></div>
                <div><dt>List received</dt><dd>{selectedRecord.assigned_at ? new Date(selectedRecord.assigned_at).toLocaleString() : '-'}</dd></div>
                <div><dt>Record created</dt><dd>{selectedRecord.record_created_at ? new Date(selectedRecord.record_created_at).toLocaleString() : '-'}</dd></div>
                <div><dt>Loan created</dt><dd>{selectedRecord.created_at ? new Date(selectedRecord.created_at).toLocaleString() : '-'}</dd></div>
                <div><dt>Last contact</dt><dd>{selectedRecord.last_contact || '-'}</dd></div>
              </dl>
            ) : (
              <div className="debt-record-editors debt-record-modal-editors">
                <form onSubmit={(event) => saveDebtorDetails(event, selectedRecord)}>
                  <strong>Client and business details</strong>
                  <label>First name<input required value={(debtorEdits[selectedRecord.debtor_id] || selectedRecord).first_name || ''} onChange={(event) => updateDebtorEdit(selectedRecord, 'first_name', event.target.value)} /></label>
                  <label>Middle and last names<input value={(debtorEdits[selectedRecord.debtor_id] || selectedRecord).other_names || ''} onChange={(event) => updateDebtorEdit(selectedRecord, 'other_names', event.target.value)} /></label>
                  <label>Agent phone<input required value={(debtorEdits[selectedRecord.debtor_id] || selectedRecord).agent_number || ''} onChange={(event) => updateDebtorEdit(selectedRecord, 'agent_number', event.target.value)} /></label>
                  <label>Owner phone<input value={(debtorEdits[selectedRecord.debtor_id] || selectedRecord).owner_msisdn || ''} onChange={(event) => updateDebtorEdit(selectedRecord, 'owner_msisdn', event.target.value)} /></label>
                  <label>Operator phone<input value={(debtorEdits[selectedRecord.debtor_id] || selectedRecord).operator_msisdn || ''} onChange={(event) => updateDebtorEdit(selectedRecord, 'operator_msisdn', event.target.value)} /></label>
                  <label>Agent number<input required value={(debtorEdits[selectedRecord.debtor_id] || selectedRecord).agent_no || ''} onChange={(event) => updateDebtorEdit(selectedRecord, 'agent_no', event.target.value)} /></label>
                  <label>Store number<input value={(debtorEdits[selectedRecord.debtor_id] || selectedRecord).store_number || ''} onChange={(event) => updateDebtorEdit(selectedRecord, 'store_number', event.target.value)} /></label>
                  <label>Business name<input required value={(debtorEdits[selectedRecord.debtor_id] || selectedRecord).business_name || ''} onChange={(event) => updateDebtorEdit(selectedRecord, 'business_name', event.target.value)} /></label>
                  <label>Physical location<input value={(debtorEdits[selectedRecord.debtor_id] || selectedRecord).business_location || ''} onChange={(event) => updateDebtorEdit(selectedRecord, 'business_location', event.target.value)} /></label>
                  <div className="debt-edit-action"><button className="leave-primary-button" type="submit">Update client details</button></div>
                </form>
                <form onSubmit={(event) => saveLoanDetails(event, selectedRecord)}>
                  <strong>Loan details</strong>
                  <label>Original loan amount<input type="number" min="0.01" step="0.01" required value={loanEdits[selectedRecord.id]?.loan_amount ?? selectedRecord.loan_amount} onChange={(event) => setLoanEdits((current) => ({ ...current, [selectedRecord.id]: { ...current[selectedRecord.id], loan_amount: event.target.value } }))} /></label>
                  <label>Disbursed date<input type="date" required value={loanEdits[selectedRecord.id]?.loan_date ?? selectedRecord.loan_date ?? ''} onChange={(event) => setLoanEdits((current) => ({ ...current, [selectedRecord.id]: { ...current[selectedRecord.id], loan_date: event.target.value } }))} /></label>
                  <label>Last interest calculation<input type="date" value={loanEdits[selectedRecord.id]?.last_interest_calc_date ?? selectedRecord.last_interest_calc_date ?? ''} onChange={(event) => setLoanEdits((current) => ({ ...current, [selectedRecord.id]: { ...current[selectedRecord.id], last_interest_calc_date: event.target.value || null } }))} /></label>
                  <label>Status<select value={loanEdits[selectedRecord.id]?.status ?? selectedRecord.status} onChange={(event) => setLoanEdits((current) => ({ ...current, [selectedRecord.id]: { ...current[selectedRecord.id], status: event.target.value } }))}>{Object.entries(statusLabels).filter(([value]) => value !== 'written_off').map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label>
                  <div className="debt-edit-action"><button className="leave-primary-button" type="submit">Update loan details</button></div>
                </form>
              </div>
            )}
            {recordPanel.mode === 'view' && !archiveView && (
              <label className="debt-record-assignment">
                Assign to collector
                <select
                  aria-label={`Assign ${selectedRecord.agent_name} to collector`}
                  value={selectedRecord.collector_id || ''}
                  onChange={(event) => assignLoan(selectedRecord.id, event.target.value)}
                >
                  <option value="">Unassigned</option>
                  {allocationCollectors.map((collector) => (
                    <option key={collector.id} value={collector.id}>{collector.full_name}</option>
                  ))}
                </select>
              </label>
            )}
          </section>
        </div>
      )}
    </section>
  );
}
