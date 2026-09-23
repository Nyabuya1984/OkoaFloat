import React from 'react';
import { ReportTable } from './ReportTable';

export const DrillDownModal = ({ rows = [], onClose }) => <div className="sales-v2-modal-backdrop" role="presentation" onClick={onClose}><div className="sales-v2-modal" role="dialog" aria-modal="true" aria-labelledby="sales-drilldown-title" onClick={(event) => event.stopPropagation()}><div className="sales-v2-heading"><h2 id="sales-drilldown-title">Visit detail</h2><button type="button" className="sales-v2-close" onClick={onClose} aria-label="Close visit detail">x</button></div><ReportTable rows={rows} /></div></div>;
