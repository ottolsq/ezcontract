<script setup>
const props = defineProps({
  modelValue: { type: Object, required: true },
  artists: { type: Array, default: () => [] },
  eventTypeOptions: { type: Array, default: () => [] },
})
const emit = defineEmits(['update:modelValue'])

function update(field, value) {
  emit('update:modelValue', { ...props.modelValue, [field]: value })
}
</script>

<template>
  <div class="form-grid">
    <div class="form-item">
      <label class="required">人员</label>
      <el-select :modelValue="modelValue.artist_id" @update:modelValue="v => update('artist_id', v)" placeholder="选择人员" size="small" style="width: 100%">
        <el-option v-for="a in artists" :key="a.id" :label="a.name" :value="a.id" />
      </el-select>
    </div>
    <div class="form-item">
      <label class="required">日期</label>
      <el-date-picker :modelValue="modelValue.event_date" @update:modelValue="v => update('event_date', v)" type="date" placeholder="选择日期" size="small" value-format="YYYY-MM-DD" style="width: 100%" />
    </div>
    <div class="form-item">
      <label>时间段</label>
      <div class="time-range">
        <el-time-picker :modelValue="modelValue.start_time" @update:modelValue="v => update('start_time', v)" placeholder="开始" size="small" value-format="HH:mm" style="width: 100%" />
        <span>~</span>
        <el-time-picker :modelValue="modelValue.end_time" @update:modelValue="v => update('end_time', v)" placeholder="结束" size="small" value-format="HH:mm" style="width: 100%" />
      </div>
    </div>
    <div class="form-item">
      <label class="required">行程事项</label>
      <el-input :modelValue="modelValue.title" @update:modelValue="v => update('title', v)" placeholder="如：品牌发布会" size="small" />
    </div>
    <div class="form-item">
      <label>事项类型</label>
      <el-select :modelValue="modelValue.event_type" @update:modelValue="v => update('event_type', v)" placeholder="类型" size="small" style="width: 100%">
        <el-option v-for="opt in eventTypeOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
      </el-select>
    </div>
    <div class="form-item">
      <label>地点</label>
      <el-input :modelValue="modelValue.location" @update:modelValue="v => update('location', v)" placeholder="地点" size="small" />
    </div>
    <div class="form-item wide">
      <label>内容摘要</label>
      <el-input :modelValue="modelValue.summary" @update:modelValue="v => update('summary', v)" type="textarea" :rows="2" placeholder="活动内容摘要" size="small" />
    </div>
    <div class="form-item">
      <label>随行/对接人</label>
      <el-input :modelValue="modelValue.contacts" @update:modelValue="v => update('contacts', v)" placeholder="对接人姓名" size="small" />
    </div>
    <div class="form-item">
      <label>物料准备</label>
      <el-input :modelValue="modelValue.materials" @update:modelValue="v => update('materials', v)" placeholder="需要准备的物料" size="small" />
    </div>
    <div class="form-item wide">
      <label>备注</label>
      <el-input :modelValue="modelValue.notes" @update:modelValue="v => update('notes', v)" type="textarea" :rows="2" placeholder="其他备注" size="small" />
    </div>
  </div>
</template>

<style scoped>
.form-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
}

.form-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.form-item.wide {
  grid-column: span 3;
}

.form-item label {
  font-size: 12px;
  color: #66758a;
}

.form-item label.required::after {
  content: '*';
  color: #e74c3c;
  margin-left: 2px;
}

.time-range {
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  align-items: center;
  gap: 6px;
}

@media (max-width: 768px) {
  .form-grid {
    grid-template-columns: repeat(2, 1fr);
  }

  .form-item.wide {
    grid-column: span 2;
  }
}

@media (max-width: 480px) {
  .form-grid {
    grid-template-columns: 1fr;
  }

  .form-item.wide {
    grid-column: span 1;
  }
}
</style>
