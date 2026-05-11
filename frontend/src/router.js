import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/', name: 'Workbench', component: () => import('./views/WorkbenchView.vue') },
  { path: '/library', name: 'Library', component: () => import('./views/LibraryView.vue') },
  { path: '/voices', name: 'Voices', component: () => import('./views/VoiceManage.vue') },
  { path: '/settings', name: 'Settings', component: () => import('./views/Settings.vue') },
  { path: '/ai-generate', redirect: '/' },
  { path: '/history', redirect: '/library' },
  { path: '/playlists', redirect: '/library' },
]

export default createRouter({
  history: createWebHistory(),
  routes,
})
