<template>
  <div class="library-page">
    <div class="library-grid">
      <section class="surface">
        <div class="surface-header">
          <div>
            <h2>音频库</h2>
            <p>按长文本分组聚合，先看一条作品，再展开看分段细节。</p>
          </div>
          <div class="surface-actions">
            <el-input v-model="query.keyword" placeholder="搜索标题、音色或正文" clearable class="search-input" @keyup.enter="reloadGroups" />
            <el-switch v-model="query.favoriteOnly" inline-prompt active-text="收藏" inactive-text="全部" @change="reloadGroups" />
            <el-button @click="reloadGroups" :loading="groupsLoading">刷新</el-button>
          </div>
        </div>

        <div v-if="groupsError" class="inline-state">
          <span>{{ groupsError }}</span>
          <el-button link type="primary" @click="reloadGroups">重试</el-button>
        </div>

        <el-table v-else :data="groups" row-key="group_id" empty-text="还没有音频结果">
          <el-table-column prop="title" label="标题" min-width="280" show-overflow-tooltip />
          <el-table-column prop="voice_name" label="音色" width="130" />
          <el-table-column label="片段" width="90">
            <template #default="{ row }">{{ row.clip_count }}</template>
          </el-table-column>
          <el-table-column label="总时长" width="110">
            <template #default="{ row }">{{ formatDuration(row.total_duration) }}</template>
          </el-table-column>
          <el-table-column label="来源" width="100">
            <template #default="{ row }">
              <el-tag size="small" :type="row.source_type === 'long_text' ? 'primary' : 'info'">
                {{ row.source_type === 'long_text' ? '长文本' : '单条' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="收藏" width="90">
            <template #default="{ row }">
              <el-tag size="small" :type="row.has_favorite ? 'warning' : 'info'">{{ row.has_favorite ? '已收藏' : '未收藏' }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="时间" width="170">
            <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="320" fixed="right">
            <template #default="{ row }">
              <el-button size="small" @click="openGroup(row.group_id)">详情</el-button>
              <el-button size="small" type="success" @click="playGroup(row.group_id)">播放</el-button>
              <el-button size="small" :disabled="!selectedPlaylistId" @click="addGroupToPlaylist(row.group_id)">加入当前列表</el-button>
              <el-button size="small" type="danger" @click="deleteGroupItem(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>

        <div class="pagination-row">
          <el-pagination
            background
            layout="prev, pager, next, total"
            :total="total"
            :page-size="query.size"
            :current-page="query.page"
            @current-change="handlePageChange"
          />
        </div>
      </section>

      <aside class="surface side-surface">
        <div class="surface-header">
          <div>
            <h2>播放列表</h2>
            <p>选定一个当前列表后，音频库里的“加入”操作都会落到这里。</p>
          </div>
          <el-button type="primary" @click="createDialogOpen = true">新建列表</el-button>
        </div>

        <el-empty v-if="!playlists.length" description="还没有播放列表" :image-size="90" />

        <div v-else class="playlist-stack">
          <button
            v-for="playlist in playlists"
            :key="playlist.id"
            class="playlist-button"
            :class="{ active: playlist.id === selectedPlaylistId }"
            @click="selectPlaylist(playlist.id)"
          >
            <span>{{ playlist.name }}</span>
            <span>{{ playlist.description || '未填写描述' }}</span>
          </button>
        </div>

        <div v-if="selectedPlaylist" class="playlist-detail">
          <div class="playlist-detail-header">
            <div>
              <div class="detail-title">{{ selectedPlaylist.name }}</div>
              <div class="detail-subtitle">{{ selectedPlaylist.description || '当前接收列表' }}</div>
            </div>
            <el-button type="danger" plain size="small" @click="deletePlaylistItem(selectedPlaylist)">删除</el-button>
          </div>

          <el-table :data="playlistTracks" size="small" empty-text="这个列表还是空的">
            <el-table-column label="标题" min-width="180">
              <template #default="{ row }">{{ row.audio.title }}</template>
            </el-table-column>
            <el-table-column label="时长" width="100">
              <template #default="{ row }">{{ formatDuration(row.audio.duration) }}</template>
            </el-table-column>
            <el-table-column label="操作" width="150">
              <template #default="{ row }">
                <el-button size="small" @click="playTrack(row.audio)">播放</el-button>
                <el-button size="small" type="danger" @click="removePlaylistTrack(row)">移除</el-button>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </aside>
    </div>

    <el-dialog v-model="createDialogOpen" title="新建播放列表" width="420px">
      <el-form label-position="top">
        <el-form-item label="名称">
          <el-input v-model="newPlaylist.name" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="newPlaylist.description" type="textarea" :rows="3" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createDialogOpen = false">取消</el-button>
        <el-button type="primary" @click="savePlaylist">创建</el-button>
      </template>
    </el-dialog>

    <el-drawer v-model="groupDrawerOpen" size="860px" :title="groupDetail?.title || '音频详情'">
      <div v-if="groupDetail" class="group-detail">
        <div class="detail-header-grid">
          <div class="detail-stat">
            <span>音色</span>
            <strong>{{ groupDetail.voice_name || '未记录' }}</strong>
          </div>
          <div class="detail-stat">
            <span>片段数</span>
            <strong>{{ groupDetail.clip_count }}</strong>
          </div>
          <div class="detail-stat">
            <span>总时长</span>
            <strong>{{ formatDuration(groupDetail.total_duration) }}</strong>
          </div>
          <div class="detail-stat">
            <span>来源</span>
            <strong>{{ groupDetail.source_type === 'long_text' ? '长文本' : '单条' }}</strong>
          </div>
        </div>

        <div class="surface-actions detail-actions">
          <el-button type="success" @click="playGroup(groupDetail.group_id)">播放整组</el-button>
          <el-button :disabled="!selectedPlaylistId" @click="addGroupToPlaylist(groupDetail.group_id)">加入当前列表</el-button>
          <el-button type="danger" @click="deleteGroupItem(groupDetail)">删除整组</el-button>
        </div>

        <el-table :data="groupDetail.records" empty-text="没有可展示的片段">
          <el-table-column label="序号" width="70">
            <template #default="{ row, $index }">{{ row.chunk_index || row.chunk_index === 0 ? row.chunk_index + 1 : $index + 1 }}</template>
          </el-table-column>
          <el-table-column prop="title" label="标题" min-width="180" show-overflow-tooltip />
          <el-table-column label="时长" width="100">
            <template #default="{ row }">{{ formatDuration(row.duration) }}</template>
          </el-table-column>
          <el-table-column label="收藏" width="90">
            <template #default="{ row }">
              <el-button text @click="toggleRecordFavorite(row)">{{ row.is_favorite ? '取消收藏' : '收藏' }}</el-button>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="280">
            <template #default="{ row }">
              <el-button size="small" @click="playTrack(row)">播放</el-button>
              <el-button size="small" @click="downloadRecord(row)">下载</el-button>
              <el-button size="small" :disabled="!selectedPlaylistId" @click="addRecordToPlaylist(row.id)">加入当前列表</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { addTrack, createPlaylist, deletePlaylist, getPlaylists, getTracks, removeTrack } from '../api/playlists'
import { deleteAudioGroup, getAudioGroup, getAudioGroups, getAudioUrl, toggleFavorite } from '../api/audio'
import { formatDate, formatDuration } from '../utils/format'
import { usePlayerStore } from '../stores/player'

const player = usePlayerStore()

const groups = ref([])
const total = ref(0)
const groupsLoading = ref(false)
const groupsError = ref('')

const playlists = ref([])
const selectedPlaylistId = ref(null)
const playlistTracks = ref([])
const createDialogOpen = ref(false)
const groupDrawerOpen = ref(false)
const groupDetail = ref(null)

const query = reactive({
  keyword: '',
  favoriteOnly: false,
  page: 1,
  size: 20,
})

const newPlaylist = reactive({
  name: '',
  description: '',
})

const selectedPlaylist = computed(() => playlists.value.find(item => item.id === selectedPlaylistId.value) || null)

onMounted(async () => {
  await Promise.all([reloadGroups(), loadPlaylists()])
})

async function reloadGroups() {
  groupsLoading.value = true
  groupsError.value = ''
  try {
    const { data } = await getAudioGroups({
      page: query.page,
      size: query.size,
      q: query.keyword || undefined,
      favorite: query.favoriteOnly ? true : undefined,
    })
    groups.value = data.items || []
    total.value = data.total || 0
  } catch (error) {
    groupsError.value = error.response?.data?.detail || '加载音频库失败'
  } finally {
    groupsLoading.value = false
  }
}

async function loadPlaylists() {
  try {
    const { data } = await getPlaylists()
    playlists.value = data
    if (!selectedPlaylistId.value && data.length) {
      await selectPlaylist(data[0].id)
    } else if (selectedPlaylistId.value) {
      await loadPlaylistTracks(selectedPlaylistId.value)
    }
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || '加载播放列表失败')
  }
}

async function selectPlaylist(playlistId) {
  selectedPlaylistId.value = playlistId
  await loadPlaylistTracks(playlistId)
}

async function loadPlaylistTracks(playlistId) {
  if (!playlistId) {
    playlistTracks.value = []
    return
  }
  try {
    const { data } = await getTracks(playlistId)
    playlistTracks.value = data
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || '加载列表内容失败')
  }
}

async function savePlaylist() {
  if (!newPlaylist.name.trim()) {
    ElMessage.warning('请先填写列表名称')
    return
  }
  try {
    const { data } = await createPlaylist({
      name: newPlaylist.name.trim(),
      description: newPlaylist.description.trim() || null,
    })
    createDialogOpen.value = false
    newPlaylist.name = ''
    newPlaylist.description = ''
    await loadPlaylists()
    await selectPlaylist(data.id)
    ElMessage.success('播放列表已创建')
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || '创建失败')
  }
}

async function deletePlaylistItem(playlist) {
  try {
    await ElMessageBox.confirm(`确认删除播放列表「${playlist.name}」？`, '删除列表')
    await deletePlaylist(playlist.id)
    if (selectedPlaylistId.value === playlist.id) {
      selectedPlaylistId.value = null
      playlistTracks.value = []
    }
    await loadPlaylists()
    ElMessage.success('播放列表已删除')
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error(error.response?.data?.detail || error.message || '删除失败')
    }
  }
}

async function openGroup(groupId) {
  try {
    const { data } = await getAudioGroup(groupId)
    groupDetail.value = data
    groupDrawerOpen.value = true
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || '加载分组详情失败')
  }
}

async function playGroup(groupId) {
  const detail = groupDetail.value?.group_id === groupId ? groupDetail.value : (await getAudioGroup(groupId)).data
  if (detail.group_id !== groupId) {
    groupDetail.value = detail
  }
  const queue = detail.records.map(record => ({
    id: record.id,
    title: record.title,
    sourceType: 'record',
  }))
  player.setQueue(queue, { label: detail.title })
  player.play(queue[0])
}

function playTrack(record) {
  player.play({
    id: record.id,
    title: record.title,
    sourceType: 'record',
  })
}

function downloadRecord(record) {
  const link = document.createElement('a')
  link.href = getAudioUrl(record.id)
  link.download = `${record.title || 'audio'}.wav`
  link.click()
}

async function toggleRecordFavorite(record) {
  try {
    await toggleFavorite(record.id)
    await Promise.all([reloadGroups(), groupDetail.value ? openGroup(groupDetail.value.group_id) : Promise.resolve()])
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || '操作失败')
  }
}

async function addRecordToPlaylist(audioId) {
  if (!selectedPlaylistId.value) {
    ElMessage.warning('请先在右侧选一个播放列表')
    return
  }
  try {
    await addTrack(selectedPlaylistId.value, audioId)
    await loadPlaylistTracks(selectedPlaylistId.value)
    ElMessage.success('已加入当前播放列表')
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || '加入失败')
  }
}

async function addGroupToPlaylist(groupId) {
  if (!selectedPlaylistId.value) {
    ElMessage.warning('请先在右侧选一个播放列表')
    return
  }
  try {
    const detail = groupDetail.value?.group_id === groupId ? groupDetail.value : (await getAudioGroup(groupId)).data
    for (const record of detail.records) {
      await addTrack(selectedPlaylistId.value, record.id)
    }
    await loadPlaylistTracks(selectedPlaylistId.value)
    ElMessage.success(`已把 ${detail.records.length} 段加入当前列表`)
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || '加入失败')
  }
}

async function removePlaylistTrack(track) {
  if (!selectedPlaylistId.value) return
  try {
    await removeTrack(selectedPlaylistId.value, track.track_id)
    await loadPlaylistTracks(selectedPlaylistId.value)
    ElMessage.success('已从播放列表移除')
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || '移除失败')
  }
}

async function deleteGroupItem(group) {
  try {
    await ElMessageBox.confirm(`确认删除「${group.title}」整组音频？`, '删除音频组')
    await deleteAudioGroup(group.group_id)
    if (groupDetail.value?.group_id === group.group_id) {
      groupDrawerOpen.value = false
      groupDetail.value = null
    }
    await Promise.all([reloadGroups(), loadPlaylists()])
    ElMessage.success('音频分组已删除')
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error(error.response?.data?.detail || error.message || '删除失败')
    }
  }
}

function handlePageChange(page) {
  query.page = page
  reloadGroups()
}
</script>

<style scoped>
.library-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.6fr) minmax(320px, 0.95fr);
  gap: 20px;
  align-items: start;
}

.surface {
  background: #fff;
  border: 1px solid #e8edf5;
  border-radius: 8px;
  padding: 20px;
}

.surface-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  margin-bottom: 16px;
}

.surface-header h2 {
  margin: 0;
  font-size: 20px;
}

.surface-header p {
  margin: 6px 0 0;
  font-size: 13px;
  color: #64748b;
}

.surface-actions {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}

.search-input {
  width: 240px;
}

.pagination-row {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}

.playlist-stack,
.group-detail {
  display: grid;
  gap: 12px;
}

.playlist-button {
  background: #f8fafc;
  border: 1px solid #e8edf5;
  border-radius: 8px;
  padding: 12px;
  text-align: left;
  display: grid;
  gap: 6px;
  cursor: pointer;
}

.playlist-button span:first-child {
  font-size: 14px;
  font-weight: 600;
  color: #0f172a;
}

.playlist-button span:last-child {
  font-size: 12px;
  color: #64748b;
}

.playlist-button.active {
  border-color: #60a5fa;
  background: #eff6ff;
}

.playlist-detail {
  margin-top: 18px;
  padding-top: 18px;
  border-top: 1px solid #eef2f8;
}

.playlist-detail-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 12px;
}

.detail-title {
  font-size: 15px;
  font-weight: 600;
  color: #0f172a;
}

.detail-subtitle {
  margin-top: 4px;
  font-size: 12px;
  color: #64748b;
}

.inline-state {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  color: #b45309;
  font-size: 13px;
  margin-bottom: 16px;
}

.detail-header-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.detail-stat {
  background: #f8fafc;
  border: 1px solid #e8edf5;
  border-radius: 8px;
  padding: 12px;
  display: grid;
  gap: 6px;
}

.detail-stat span {
  font-size: 12px;
  color: #64748b;
}

.detail-stat strong {
  font-size: 15px;
  color: #0f172a;
}

.detail-actions {
  margin: 16px 0;
}
</style>
