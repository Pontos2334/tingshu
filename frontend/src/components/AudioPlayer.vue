<template>
  <div class="audio-player">
    <audio ref="audioEl" />
    <div class="track-meta">
      <div class="track-title">{{ player.currentTitle || '还没有开始播放' }}</div>
      <div class="track-subtitle">
        <span>{{ sourceLabel }}</span>
        <span v-if="player.queueContext?.label"> · {{ player.queueContext.label }}</span>
      </div>
    </div>

    <div class="controls">
      <el-button :icon="ArrowLeft" circle size="small" :disabled="!canStep" @click="player.playPrev()" />
      <el-button
        :icon="player.isPlaying ? VideoPause : VideoPlay"
        circle
        size="large"
        type="primary"
        :disabled="!player.hasSource"
        @click="togglePlay"
      />
      <el-button :icon="ArrowRight" circle size="small" :disabled="!canStep" @click="player.playNext()" />
    </div>

    <div class="progress">
      <el-slider
        :model-value="player.currentTime"
        :max="player.duration || 1"
        :format-tooltip="formatTime"
        @input="player.seek($event)"
      />
      <div class="time-meta">{{ formatTime(player.currentTime) }} / {{ formatTime(player.duration) }}</div>
    </div>

    <div class="toolbar">
      <el-select v-model="player.playbackRate" size="small" @change="player.setRate($event)">
        <el-option v-for="rate in rates" :key="rate" :label="`${rate}x`" :value="rate" />
      </el-select>
      <div class="volume">
        <el-icon><MuteNotification /></el-icon>
        <el-slider v-model="volume" :max="1" :step="0.1" @input="setVolume" />
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { ArrowLeft, ArrowRight, MuteNotification, VideoPause, VideoPlay } from '@element-plus/icons-vue'
import { usePlayerStore } from '../stores/player'

const player = usePlayerStore()
const audioEl = ref(null)
const volume = ref(1)
const rates = [0.75, 1, 1.25, 1.5, 2]

const canStep = computed(() => player.queue.length > 1)
const sourceLabel = computed(() => {
  const labelMap = {
    record: '音频记录',
    preview: '试听',
    external: '外部音频',
  }
  return labelMap[player.currentSourceType] || '播放器'
})

onMounted(() => {
  player.setAudio(audioEl.value)
})

function togglePlay() {
  if (player.isPlaying) {
    player.pause()
    return
  }
  if (player.hasSource) {
    player.resume()
  }
}

function setVolume(nextVolume) {
  if (audioEl.value) {
    audioEl.value.volume = nextVolume
  }
}

function formatTime(seconds) {
  if (!seconds) return '0:00'
  const minutes = Math.floor(seconds / 60)
  const remain = Math.floor(seconds % 60)
  return `${minutes}:${remain.toString().padStart(2, '0')}`
}
</script>

<style scoped>
.audio-player {
  display: grid;
  grid-template-columns: minmax(220px, 1.3fr) auto minmax(280px, 2fr) minmax(220px, 0.9fr);
  gap: 18px;
  align-items: center;
  width: 100%;
}

.track-meta {
  min-width: 0;
}

.track-title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 15px;
  font-weight: 600;
  color: #0f172a;
}

.track-subtitle {
  margin-top: 4px;
  font-size: 12px;
  color: #64748b;
}

.controls {
  display: flex;
  align-items: center;
  gap: 8px;
}

.progress {
  min-width: 0;
}

.time-meta {
  margin-top: 6px;
  font-size: 12px;
  color: #64748b;
}

.toolbar {
  display: flex;
  align-items: center;
  gap: 16px;
}

.volume {
  display: grid;
  grid-template-columns: auto minmax(90px, 120px);
  gap: 8px;
  align-items: center;
  color: #64748b;
}

@media (max-width: 1100px) {
  .audio-player {
    grid-template-columns: minmax(160px, 1.3fr) auto minmax(200px, 2fr) minmax(160px, 0.9fr);
    gap: 12px;
  }
}

@media (max-width: 900px) {
  .audio-player {
    grid-template-columns: 1fr auto 1fr;
    gap: 10px;
  }
  .toolbar {
    display: none;
  }
}

@media (max-width: 700px) {
  .audio-player {
    grid-template-columns: 1fr auto;
    gap: 8px;
  }
  .progress {
    display: none;
  }
}
</style>
