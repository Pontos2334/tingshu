import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import './assets/styles/main.css'

const app = createApp(App)

app.config.errorHandler = (err, instance, info) => {
  console.error('Vue 全局错误:', err, info)
  ElMessage.error('应用发生错误，请刷新页面重试')
}

app.use(createPinia())
app.use(router)
app.mount('#app')
