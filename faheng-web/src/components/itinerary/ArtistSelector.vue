<script setup>
import { ref, computed } from 'vue'
import { Plus, Delete } from '@element-plus/icons-vue'
import { ElMessageBox } from 'element-plus'
import { useItineraryStore } from '../../stores/itinerary'

const store = useItineraryStore()
const addName = ref('')
const addDialogVisible = ref(false)

const selectedLabel = computed(() => {
  const artist = store.selectedArtist
  return artist ? artist.name : '选择艺人'
})

async function openAddDialog() {
  addName.value = ''
  addDialogVisible.value = true
}

async function submitAdd() {
  const name = addName.value.trim()
  if (!name) return
  await store.createArtist(name)
  addDialogVisible.value = false
  addName.value = ''
}

async function remove(artist) {
  try {
    await ElMessageBox.confirm(`删除艺人「${artist.name}」将同时删除其全部行程，确定吗？`, '确认删除', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning',
    })
    await store.deleteArtist(artist.id)
  } catch {
    // cancel
  }
}
</script>

<template>
  <div class="artist-bar">
    <div class="artist-select-row">
      <div class="select-wrap">
        <span class="dot" :style="{ background: store.selectedArtist?.color || '#2459a9' }"></span>
        <el-select
          :model-value="store.selectedArtistId"
          placeholder="选择艺人"
          size="default"
          style="width: 180px"
          @update:model-value="store.selectArtist"
        >
          <template #header>
            <div class="dropdown-header">选择艺人</div>
          </template>
          <el-option
            v-for="artist in store.artists"
            :key="artist.id"
            :label="artist.name"
            :value="artist.id"
          >
            <div class="artist-option">
              <span class="option-dot" :style="{ background: artist.color }"></span>
              <span class="option-name">{{ artist.name }}</span>
              <span class="option-count">{{ artist.event_count || 0 }}</span>
              <el-icon class="option-del" @click.stop="remove(artist)"><Delete /></el-icon>
            </div>
          </el-option>
        </el-select>
      </div>

      <el-button type="primary" plain size="small" :icon="Plus" @click="openAddDialog">
        新增艺人
      </el-button>
    </div>

    <div v-if="store.selectedArtist" class="current-artist">
      当前艺人：<b :style="{ color: store.selectedArtist.color }">{{ store.selectedArtist.name }}</b>
    </div>

    <el-dialog
      v-model="addDialogVisible"
      title="新增艺人"
      width="360px"
      :close-on-click-modal="false"
    >
      <el-input v-model="addName" placeholder="请输入艺人姓名" @keyup.enter="submitAdd" />
      <template #footer>
        <el-button size="small" @click="addDialogVisible = false">取消</el-button>
        <el-button type="primary" size="small" @click="submitAdd">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.artist-bar {
  margin-bottom: 14px;
  flex-shrink: 0;
  background: #fff;
  border: 1px solid #e4e9f2;
  border-radius: 12px;
  padding: 12px 16px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}

.artist-select-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.select-wrap {
  display: flex;
  align-items: center;
  gap: 8px;
}

.dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}

.current-artist {
  font-size: 13px;
  color: #66758a;
}

.current-artist b {
  font-weight: 600;
}

.dropdown-header {
  padding: 6px 12px;
  font-size: 12px;
  color: #9aabbe;
  border-bottom: 1px solid #f0f0f0;
  margin-bottom: 4px;
}

.artist-option {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 2px 0;
}

.option-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.option-name {
  flex: 1;
  color: #1d2b4f;
  font-size: 14px;
}

.option-count {
  font-size: 12px;
  color: #9aabbe;
  background: #f0f4fa;
  border-radius: 999px;
  padding: 1px 7px;
}

.option-del {
  font-size: 13px;
  color: #9aabbe;
  opacity: 0;
  transition: opacity 0.15s;
  padding: 2px;
}

.artist-option:hover .option-del {
  opacity: 1;
}

.option-del:hover {
  color: #e74c3c;
}

@media (max-width: 768px) {
  .artist-bar {
    flex-direction: column;
    align-items: flex-start;
    gap: 10px;
    padding: 12px;
  }

  .artist-select-row {
    width: 100%;
  }

  .select-wrap {
    flex: 1;
  }

  .select-wrap :deep(.el-select) {
    width: 100% !important;
  }

  .current-artist {
    width: 100%;
  }
}
</style>
