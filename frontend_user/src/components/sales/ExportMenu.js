import React from 'react';
import { getAuthToken } from '../../services/authStorage';
import { apiUrl } from '../../services/apiConfig';

const downloadWithAuth = async (url, filename) => {
  const token = getAuthToken();
  const response = await fetch(url, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });

  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload?.error?.message || payload?.msg || 'Unable to export sales data.');
  }

  const blob = await response.blob();
  const blobUrl = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = blobUrl;
  anchor.download = filename;
  anchor.rel = 'noopener noreferrer';
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(blobUrl);
};

export const ExportMenu = ({ exportUrl }) => {
  const download = async (format) => {
    try {
      const baseUrl = exportUrl || apiUrl('/api/sales/v2/export.csv?scope=team');
      const url = format === 'csv' ? baseUrl : baseUrl.replace('.csv', '.xlsx');
      await downloadWithAuth(url, format === 'csv' ? 'sales-reports.csv' : 'sales-reports.xlsx');
    } catch (error) {
      window.alert(error.message || 'Unable to export sales data.');
    }
  };

  const share = () => {
    const link = window.location.href;
    window.open(`https://wa.me/?text=${encodeURIComponent(link)}`, '_blank', 'noopener,noreferrer');
  };

  return (
    <div className="sales-v2-export">
      <button type="button" onClick={() => download('csv')}>Export CSV</button>
      <button type="button" onClick={() => download('xlsx')}>Export Excel</button>
      <button type="button" onClick={share}>Share</button>
      {getAuthToken() ? null : <small>Sign in to export</small>}
    </div>
  );
};
