<script setup>
/**
 * 通用加载指示器（三模块统一风格 + 差异化图标/颜色）
 *
 * @prop {string} type - 模块类型：'draft' | 'review' | 'compliance'
 * @prop {number} percentage - 进度百分比（0-100）
 * @prop {string} stage - 当前阶段文案（如"正在识别条款..."）
 * @prop {string} title - 主标题（如"正在提取履约节点"）
 * @prop {string} subtitle - 副标题（如文件名）
 */
import { onMounted } from 'vue'

const props = defineProps({
  type: {
    type: String,
    required: true,
    validator: (v) => ['draft', 'review', 'compliance'].includes(v),
  },
  percentage: {
    type: Number,
    default: 0,
  },
  stage: {
    type: String,
    default: '',
  },
  title: {
    type: String,
    default: '',
  },
  subtitle: {
    type: String,
    default: '',
  },
})

const CONFIG = {
  draft: {
    icon: '✏️',
    color: '#3498db',
    bgColor: '#eaf6ff',
    title: '正在生成合同模板',
    animate: true,
  },
  review: {
    icon: '🛡️',
    color: '#f39c12',
    bgColor: '#fef5e7',
    title: '正在进行 AI 审查',
    animate: true,
  },
  compliance: {
    icon: '🔔',
    color: '#27ae60',
    bgColor: '#e8f8f2',
    title: '正在提取履约节点',
    animate: true,
  },
}

const config = CONFIG[props.type]

// 组件挂载时移除焦点，防止光标闪烁
onMounted(() => {
  if (document.activeElement) {
    document.activeElement.blur()
  }
})
</script>

<template>
  <div class="loading-indicator">
    <!-- 圆形图标 -->
    <div
      class="icon-circle"
      :class="{ animate: config.animate }"
      :style="{ background: config.bgColor, color: config.color }"
    >
      <span class="icon">{{ config.icon }}</span>
    </div>

    <!-- 标题 -->
    <h2>{{ title || config.title }}</h2>

    <!-- 副标题 -->
    <p v-if="subtitle" class="subtitle">{{ subtitle }}</p>

    <!-- 进度条容器 -->
    <div class="progress-wrapper">
      <el-progress
        :percentage="percentage"
        :stroke-width="10"
        :show-text="false"
        :color="config.color"
        class="progress-bar"
      />
    </div>

    <!-- 阶段文案 -->
    <p v-if="stage" class="stage">{{ stage }}</p>
  </div>
</template>

<style scoped>
.loading-indicator {
  width: 100%;
  margin: 60px auto;
  text-align: center;
  padding: 20px 0;
  box-sizing: border-box;
}

.icon-circle {
  width: 88px;
  height: 88px;
  margin: 0 auto 22px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  font-size: 36px;
  position: relative;
}

.icon-circle.animate {
  animation: spin 1.6s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.icon {
  display: block;
}

h2 {
  margin: 0 0 6px;
  font-size: 20px;
  color: #1d2b4f;
  min-height: 28px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.subtitle {
  color: #66758a;
  font-size: 13px;
  margin-bottom: 22px;
  min-height: 20px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.progress-wrapper {
  width: 400px;
  margin: 0 auto 10px;
}

.progress-bar {
  width: 100% !important;
}

.progress-bar :deep(.el-progress-bar) {
  width: 100% !important;
}

.progress-bar :deep(.el-progress-bar__outer) {
  width: 100% !important;
}

.stage {
  color: #66758a;
  font-size: 13px;
  min-height: 20px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
