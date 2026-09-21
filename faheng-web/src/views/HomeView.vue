<script setup>
import { useRouter } from 'vue-router'

const router = useRouter()
const today = new Date().toLocaleDateString('zh-CN')
</script>

<template>
  <div class="home">
    <header class="hero">
      <div class="brand">⚖️ 法衡 AI</div>
      <h1>企业多智能体工作台</h1>
      <p class="lead">
        合同起草、风险审查等企业智能体持续扩展中 —— AI 负责识别与生成，人负责确认与决策。
      </p>
    </header>

    <div class="cards">
      <div class="card" @click="router.push('/draft')">
        <div class="card-icon">📝</div>
        <h2>合同起草智能体</h2>
        <p>输入关键词，AI 生成结构完整的合同模板；在线编辑、对话式修订，一键导出 Word。</p>
        <div class="flow">关键词 → 生成模板 → 调整 → 导出 .docx</div>
      </div>

      <div class="card" @click="router.push('/review')">
        <div class="card-icon">🛡️</div>
        <h2>合同审查智能体</h2>
        <p>上传 PDF / Word 合同，AI 按企业规则库逐条审查；采纳、修改或驳回，导出修改后合同与审核报告。</p>
        <div class="flow">上传 → AI 审查 → 三栏工作台 → 导出</div>
      </div>

      <div class="card card-coming">
        <div class="card-icon">🔔</div>
        <h2>履约提醒 <span class="tag">规划中</span></h2>
        <p>自动提取付款日、交付日等履约节点，到期前智能提醒。</p>
      </div>

      <div class="card card-coming">
        <div class="card-icon">🗒️</div>
        <h2>会议纪要 <span class="tag">规划中</span></h2>
        <p>语音转写自动生成结构化纪要，待办事项自动提取。</p>
      </div>
    </div>

    <footer class="hint">Demo 演示环境 · 审查依据：ERP 采购合同规则库（26 条）· {{ today }}</footer>
  </div>
</template>

<style scoped>
.home {
  max-width: 980px;
  margin: 0 auto;
  padding: 48px 24px;
}

.hero {
  text-align: center;
  margin-bottom: 40px;
}

.brand {
  color: #2459a9;
  font-weight: 600;
  margin-bottom: 12px;
}

h1 {
  font-size: 34px;
  margin: 0 0 14px;
}

.lead {
  color: #66758a;
  max-width: 560px;
  margin: 0 auto;
  line-height: 1.7;
}

.cards {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
}

.card {
  background: #fff;
  border: 1px solid #e4e9f2;
  border-radius: 16px;
  padding: 28px;
  cursor: pointer;
  transition:
    transform 0.2s,
    box-shadow 0.2s;
}

.card:hover {
  transform: translateY(-4px);
  box-shadow: 0 14px 36px rgba(36, 89, 169, 0.12);
}

.card-coming {
  cursor: default;
  background: #fafbfd;
  border-style: dashed;
}

.card-coming:hover {
  transform: none;
  box-shadow: none;
}

.card-coming .card-icon {
  opacity: 0.5;
}

.tag {
  display: inline-block;
  font-size: 11px;
  font-weight: 400;
  color: #9aabbe;
  background: #f0f4fa;
  border-radius: 999px;
  padding: 2px 8px;
  margin-left: 6px;
  vertical-align: middle;
}

.card-icon {
  font-size: 34px;
  margin-bottom: 10px;
}

h2 {
  margin: 0 0 10px;
  font-size: 20px;
}

.card p {
  color: #66758a;
  line-height: 1.7;
  margin: 0 0 14px;
}

.flow {
  font-size: 12px;
  color: #2459a9;
  background: #eaf2ff;
  border-radius: 999px;
  padding: 5px 12px;
  display: inline-block;
}

.hint {
  text-align: center;
  color: #9aabbe;
  font-size: 12px;
  margin-top: 48px;
}
</style>
