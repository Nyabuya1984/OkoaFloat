export const DEBT_COLLECTION_IMPORT_FIELDS = [
  'first_name',
  'other_names',
  'agent_msisdn',
  'owner_msisdn',
  'operator_msisdn',
  'agent_no',
  'store_number',
  'business_name',
  'location',
  'loan_amount',
  'loan_balance',
  'amount_paid',
  'status',
  'created_at',
  'last_interest_calc_date',
  'no_of_days',
];

export const downloadDebtCollectionTemplate = () => {
  const csv = `\ufeff${DEBT_COLLECTION_IMPORT_FIELDS.join(',')}\r\n`;
  const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8;' }));
  const link = document.createElement('a');
  link.href = url;
  link.download = 'debt-collection-import-template.csv';
  link.click();
  URL.revokeObjectURL(url);
};
