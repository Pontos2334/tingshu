import axios from 'axios'
import { ElMessage } from 'element-plus'

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
    const status = error.response?.status
    const detail = error.response?.data?.detail

    if (status === 401) {
      ElMessage.error('认证失败，请检查设置')
    } else if (!status) {
      ElMessage.error('无法连接服务器，请确认后端服务正在运行')
    } else if (status >= 500) {
      ElMessage.error(detail || '服务暂时不可用，请稍后重试')
    }

    return Promise.reject(error)
  }
)

export default api
