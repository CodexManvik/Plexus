import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api';

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem('authToken');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('authToken');
      localStorage.removeItem('currentUser');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

const getData = async (promise) => {
  const response = await promise;
  return response.data;
};

export const api = {
  health: async () => getData(apiClient.get('/health')),

  uploadContract: async ({ file, metadata }) => {
    const formData = new FormData();
    formData.append('file', file);
    Object.entries(metadata).forEach(([key, value]) => {
      if (value !== undefined && value !== null && String(value).trim() !== '') {
        formData.append(key, value);
      }
    });
    return getData(
      apiClient.post('/contracts/upload', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
    );
  },

  listContracts: async (filters = {}) => getData(apiClient.get('/contracts', { params: filters })),

  searchContracts: async (query, filters = {}) =>
    getData(apiClient.get('/contracts/search', { params: { q: query, ...filters } })),

  getContractDetails: async (id) => getData(apiClient.get(`/contracts/${id}`)),
  getParameters: async (contractId) => getData(apiClient.get(`/contracts/${contractId}/parameters`)),
  getExtractionStatus: async (contractId) =>
    getData(apiClient.get(`/contracts/${contractId}/extraction-status`)),

  acquireLock: async (contractId, userId) =>
    getData(apiClient.post(`/contracts/${contractId}/lock`, { user_id: userId })),

  releaseLock: async (contractId, userId) =>
    getData(apiClient.post(`/contracts/${contractId}/unlock`, { user_id: userId })),

  updateParameter: async (contractId, paramId, payload) =>
    getData(apiClient.put(`/contracts/${contractId}/parameters/${paramId}`, payload)),

  verifyParameter: async (contractId, paramId, payload) =>
    getData(apiClient.post(`/contracts/${contractId}/parameters/${paramId}/verify`, payload)),

  addParameterBySearch: async (contractId, payload) =>
    getData(apiClient.post(`/contracts/${contractId}/search-add`, payload)),

  submitDraft: async (contractId, payload) =>
    getData(apiClient.post(`/contracts/${contractId}/submit-draft`, payload)),

  submitForApproval: async (contractId, payload) =>
    getData(apiClient.post(`/contracts/${contractId}/submit-approval`, payload)),

  approveContract: async (contractId, payload) =>
    getData(apiClient.post(`/contracts/${contractId}/approve`, payload)),

  sendBackContract: async (contractId, payload) =>
    getData(apiClient.post(`/contracts/${contractId}/send-back`, payload)),

  rejectContract: async (contractId, payload) =>
    getData(apiClient.post(`/contracts/${contractId}/reject`, payload)),

  compareContracts: async (contractId, compareToId) =>
    getData(apiClient.get(`/contracts/${contractId}/compare`, { params: { compare_to_id: compareToId } })),

  cloneContract: async (contractId, payload) =>
    getData(apiClient.post(`/contracts/${contractId}/clone`, payload)),

  getAuditTrail: async (contractId) => getData(apiClient.get(`/contracts/${contractId}/audit`)),

  getMetadataBundle: async () => getData(apiClient.get('/metadata/bundle')),
  getMetadataOptions: async (category) =>
    getData(apiClient.get('/metadata/options', { params: category ? { category } : {} })),
  createMetadataOption: async (payload) => getData(apiClient.post('/metadata/options', payload)),

  getOrganizations: async () => getData(apiClient.get('/metadata/organizations')),
  getBusinessUnits: async () => getData(apiClient.get('/metadata/business-units')),
  getLocations: async () => getData(apiClient.get('/metadata/locations')),
  getDepartments: async () => getData(apiClient.get('/metadata/departments')),
  getCustomerPartners: async () => getData(apiClient.get('/metadata/customer-partners')),
  getFinancialYears: async () => getData(apiClient.get('/metadata/financial-years')),
  getContractTypes: async () => getData(apiClient.get('/metadata/contract-types')),
  getAgreementTypes: async () => getData(apiClient.get('/metadata/agreement-types')),
  getExecutionTypes: async () => getData(apiClient.get('/metadata/execution-types')),

  listRules: async (params = {}) => getData(apiClient.get('/rules', { params })),
  createRule: async (rule) => getData(apiClient.post('/rules', rule)),
  updateRule: async (ruleId, rule) => getData(apiClient.put(`/rules/${ruleId}`, rule)),
  deleteRule: async (ruleId) => getData(apiClient.delete(`/rules/${ruleId}`)),

  getDashboard: async () => getData(apiClient.get('/dashboard')),
  getDashboardStats: async () => getData(apiClient.get('/dashboard/stats')),
  getRecentContracts: async (limit = 10) =>
    getData(apiClient.get('/dashboard/recent', { params: { limit } })),
  getPendingApprovals: async () => getData(apiClient.get('/dashboard/pending-approvals')),

  getSystemStatus: async () => getData(apiClient.get('/maintenance/status')),
  getErrorLogs: async (limit = 50) =>
    getData(apiClient.get('/maintenance/logs', { params: { limit } })),
  triggerSync: async () => getData(apiClient.post('/maintenance/sync')),
};

export default api;
