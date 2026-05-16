import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 120000,
})

api.interceptors.request.use((config) => {
  if (config.method !== 'get') {
    const token = localStorage.getItem('admin_token')
    if (token) {
      config.headers['X-Admin-Token'] = token
    }
  }
  return config
})

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (!error.response) {
      error._friendlyMessage = '无法连接服务器，请确认后端服务正在运行'
    } else if (error.response.status === 401) {
      error._friendlyMessage = '认证失败，请检查设置'
    } else if (error.response.status >= 500) {
      error._friendlyMessage = error.response.data?.detail || '服务暂时不可用，请稍后重试'
    }
    return Promise.reject(error)
  }
)

export function friendlyError(error, fallback = '操作失败') {
  return error._friendlyMessage || error.response?.data?.detail || fallback
}

export default api
