<template>
  <el-container class="shell">
    <el-aside :width="sidebarCollapsed ? '0px' : '220px'" class="shell-sidebar" :class="{ collapsed: sidebarCollapsed }">
      <div class="brand">
        <div class="brand-mark">听书</div>
        <div class="brand-subtitle">AI 听书工作台</div>
      </div>
      <el-menu :default-active="route.path" router class="nav-menu">
        <el-menu-item index="/">
          <el-icon><Files /></el-icon>
          <span>工作台</span>
        </el-menu-item>
        <el-menu-item index="/library">
          <el-icon><FolderOpened /></el-icon>
          <span>音频库</span>
        </el-menu-item>
        <el-menu-item index="/subtitle">
          <el-icon><Document /></el-icon>
          <span>字幕翻译</span>
        </el-menu-item>
        <el-menu-item index="/voices">
          <el-icon><Headset /></el-icon>
          <span>音色</span>
        </el-menu-item>
        <el-menu-item index="/settings">
          <el-icon><Setting /></el-icon>
          <span>设置</span>
        </el-menu-item>
      </el-menu>
    </el-aside>
    <el-container class="shell-main">
      <el-header class="topbar glass-panel" height="64px">
        <el-button :icon="sidebarCollapsed ? Expand : Fold" circle size="small" class="sidebar-toggle" @click="sidebarCollapsed = !sidebarCollapsed" />
        <div>
          <div class="topbar-title">{{ pageTitle }}</div>
          <div class="topbar-subtitle">把创作、合成、任务和播放收成一条顺手的链路</div>
        </div>
      </el-header>
      <el-main class="page-container">
        <router-view v-slot="{ Component }">
          <transition name="fade-slide" mode="out-in">
            <component :is="Component" />
          </transition>
        </router-view>
      </el-main>
      <el-footer height="92px" class="player-footer glass-panel">
        <AudioPlayer />
      </el-footer>
    </el-container>
  </el-container>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useRoute } from 'vue-router'
import { Files, FolderOpened, Document, Headset, Setting, Expand, Fold } from '@element-plus/icons-vue'
import AudioPlayer from './components/AudioPlayer.vue'

const route = useRoute()
const sidebarCollapsed = ref(false)

const pageTitle = computed(() => {
  const titleMap = {
    '/': '工作台',
    '/library': '音频库',
    '/subtitle': '字幕翻译',
    '/voices': '音色',
    '/settings': '设置',
  }
  return titleMap[route.path] || '听书'
})
</script>

<style scoped>
.shell {
  min-height: 100vh;
}

.shell-sidebar {
  background: var(--bg-surface);
  border-right: 1px solid rgba(226, 232, 240, 0.6);
  display: flex;
  flex-direction: column;
  transition: width 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  overflow: hidden;
}

.shell-sidebar.collapsed {
  border-right: none;
}

.shell-sidebar.collapsed .brand,
.shell-sidebar.collapsed .nav-menu {
  display: none;
}

.sidebar-toggle {
  margin-right: 16px;
  flex-shrink: 0;
  border: none;
  background: #f1f5f9;
}

.brand {
  padding: 32px 24px 24px;
}

.brand-mark {
  font-size: 24px;
  font-weight: 800;
  color: var(--el-color-primary);
  letter-spacing: -0.5px;
}

.brand-subtitle {
  margin-top: 4px;
  font-size: 12px;
  color: #94a3b8;
  font-weight: 500;
}

.nav-menu {
  border-right: none;
  padding: 0 12px;
}

.nav-menu :deep(.el-menu-item) {
  height: 48px;
  line-height: 48px;
  margin-bottom: 4px;
  border-radius: 8px;
  color: #64748b;
}

.nav-menu :deep(.el-menu-item.is-active) {
  background-color: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
  font-weight: 600;
}

.nav-menu :deep(.el-menu-item:hover) {
  background-color: #f8fafc;
}

.shell-main {
  min-width: 0;
}

.topbar {
  display: flex;
  align-items: center;
  padding: 0 32px;
  z-index: 10;
}

.topbar-title {
  font-size: 20px;
  font-weight: 700;
  color: #0f172a;
  letter-spacing: -0.5px;
}

.topbar-subtitle {
  margin-top: 2px;
  font-size: 12px;
  color: #94a3b8;
}

.page-container {
  padding: 32px;
  overflow-x: hidden;
}

.player-footer {
  display: flex;
  align-items: center;
  padding: 0 32px;
  z-index: 10;
}

@media (max-width: 1100px) {
  .shell-sidebar {
    width: 60px !important;
  }
  .brand {
    padding: 16px 8px 12px;
  }
  .brand-mark {
    font-size: 18px;
    text-align: center;
  }
  .brand-subtitle {
    display: none;
  }
  .nav-menu .el-menu-item span {
    display: none;
  }
  .topbar-subtitle {
    display: none;
  }
}

@media (max-width: 700px) {
  .shell-sidebar {
    width: 0 !important;
    border-right: none;
  }
}
</style>
