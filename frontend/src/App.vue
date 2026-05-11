<template>
  <el-container class="shell">
    <el-aside width="220px" class="shell-sidebar">
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
      <el-header class="topbar" height="64px">
        <div>
          <div class="topbar-title">{{ pageTitle }}</div>
          <div class="topbar-subtitle">把创作、合成、任务和播放收成一条顺手的链路</div>
        </div>
      </el-header>
      <el-main class="page-container">
        <router-view />
      </el-main>
      <el-footer height="92px" class="player-footer">
        <AudioPlayer />
      </el-footer>
    </el-container>
  </el-container>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { Files, FolderOpened, Headset, Setting } from '@element-plus/icons-vue'
import AudioPlayer from './components/AudioPlayer.vue'

const route = useRoute()

const pageTitle = computed(() => {
  const titleMap = {
    '/': '工作台',
    '/library': '音频库',
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
  background: #fff;
  border-right: 1px solid #e8edf5;
  display: flex;
  flex-direction: column;
}

.brand {
  padding: 24px 20px 20px;
}

.brand-mark {
  font-size: 26px;
  font-weight: 700;
  color: #1f2937;
}

.brand-subtitle {
  margin-top: 6px;
  font-size: 13px;
  color: #64748b;
}

.nav-menu {
  border-right: none;
}

.shell-main {
  min-width: 0;
}

.topbar {
  display: flex;
  align-items: center;
  padding: 0 28px;
  border-bottom: 1px solid #e8edf5;
  background: rgba(255, 255, 255, 0.92);
  backdrop-filter: blur(12px);
}

.topbar-title {
  font-size: 22px;
  font-weight: 700;
  color: #0f172a;
}

.topbar-subtitle {
  margin-top: 4px;
  font-size: 13px;
  color: #64748b;
}

.page-container {
  padding: 24px 28px 20px;
}

.player-footer {
  border-top: 1px solid #e8edf5;
  background: rgba(255, 255, 255, 0.94);
  display: flex;
  align-items: center;
  padding: 0 24px;
}
</style>
