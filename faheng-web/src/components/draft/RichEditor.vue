<script setup>
import { onBeforeUnmount, ref, watch } from 'vue'
import { EditorContent, useEditor } from '@tiptap/vue-3'
import StarterKit from '@tiptap/starter-kit'
import TextAlign from '@tiptap/extension-text-align'
import { Table } from '@tiptap/extension-table/table'
import { TableRow } from '@tiptap/extension-table/row'
import { TableCell } from '@tiptap/extension-table/cell'
import { TableHeader } from '@tiptap/extension-table/header'
import { Markdown } from 'tiptap-markdown'

const props = defineProps({
  modelValue: { type: String, default: '' },
  placeholder: { type: String, default: '在此输入合同内容……' },
})
const emit = defineEmits(['update:modelValue'])

// 防止外部赋值与用户输入之间的回写循环
let syncing = false

const editor = useEditor({
  content: '',
  extensions: [
    StarterKit.configure({
      heading: { levels: [1, 2] },
    }),
    TextAlign.configure({ types: ['heading', 'paragraph'] }),
    Table.configure({ resizable: false, HTMLAttributes: { class: 'docx-table' } }),
    TableRow,
    TableCell,
    TableHeader,
    Markdown.configure({ html: true, breaks: true, linkify: true }),
  ],
  editorProps: {
    attributes: {
      class: 'docx-prose',
      spellcheck: 'false',
    },
  },
  onUpdate({ editor }) {
    if (syncing) return
    const md = editor.storage.markdown.getMarkdown()
    emit('update:modelValue', md)
  },
  onCreate({ editor }) {
    if (props.modelValue) {
      editor.commands.setContent(props.modelValue, { emitUpdate: false })
    }
  },
})

// 外部 modelValue 变化（如 AI 修订后）→ 同步到编辑器
watch(
  () => props.modelValue,
  (val) => {
    if (!editor.value) return
    const current = editor.value.storage.markdown.getMarkdown()
    if (val === current) return
    syncing = true
    editor.value.commands.setContent(val || '', { emitUpdate: false })
    syncing = false
  },
)

onBeforeUnmount(() => {
  editor.value?.destroy()
})

// 暴露给父组件：导出 Word 时取当前 TipTap 的 HTML
defineExpose({
  getHtml: () => editor.value?.getHTML() ?? '',
})

// ---------- 工具栏动作 ----------
const actions = {
  toggleBold() { editor.value?.chain().focus().toggleBold().run() },
  toggleItalic() { editor.value?.chain().focus().toggleItalic().run() },
  setHeading(level) {
    editor.value?.chain().focus().toggleHeading({ level }).run()
  },
  setParagraph() {
    editor.value?.chain().focus().setParagraph().run()
  },
  toggleBulletList() {
    editor.value?.chain().focus().toggleBulletList().run()
  },
  toggleOrderedList() {
    editor.value?.chain().focus().toggleOrderedList().run()
  },
  setAlign(align) {
    editor.value?.chain().focus().setTextAlign(align).run()
  },
  insertTable() {
    editor.value
      ?.chain()
      .focus()
      .insertTable({ rows: 3, cols: 3, withHeaderRow: true })
      .run()
  },
  undo() { editor.value?.chain().focus().undo().run() },
  redo() { editor.value?.chain().focus().redo().run() },
}

function isActive(name, attrs = undefined) {
  return editor.value?.isActive(name, attrs) ?? false
}
</script>

<template>
  <div class="rich-editor">
    <div v-if="editor" class="toolbar" role="toolbar" aria-label="格式工具栏">
      <button
        type="button"
        class="tb-btn"
        :class="{ active: isActive('bold') }"
        title="加粗 (Ctrl+B)"
        @click="actions.toggleBold"
      >
        <strong>B</strong>
      </button>
      <button
        type="button"
        class="tb-btn"
        :class="{ active: isActive('italic') }"
        title="斜体 (Ctrl+I)"
        @click="actions.toggleItalic"
      >
        <em>I</em>
      </button>
      <span class="tb-sep" />
      <button
        type="button"
        class="tb-btn"
        :class="{ active: isActive('heading', { level: 1 }) }"
        title="大标题"
        @click="actions.setHeading(1)"
      >
        H1
      </button>
      <button
        type="button"
        class="tb-btn"
        :class="{ active: isActive('heading', { level: 2 }) }"
        title="一级标题"
        @click="actions.setHeading(2)"
      >
        H2
      </button>
      <button
        type="button"
        class="tb-btn"
        :class="{ active: isActive('paragraph') }"
        title="正文"
        @click="actions.setParagraph"
      >
        P
      </button>
      <span class="tb-sep" />
      <button
        type="button"
        class="tb-btn"
        :class="{ active: isActive('bulletList') }"
        title="无序列表"
        @click="actions.toggleBulletList"
      >
        • ≡
      </button>
      <button
        type="button"
        class="tb-btn"
        :class="{ active: isActive('orderedList') }"
        title="有序列表"
        @click="actions.toggleOrderedList"
      >
        1. ≡
      </button>
      <button
        type="button"
        class="tb-btn"
        title="插入表格"
        @click="actions.insertTable"
      >
        ▦
      </button>
      <span class="tb-sep" />
      <button
        type="button"
        class="tb-btn"
        :class="{ active: isActive({ textAlign: 'left' }) }"
        title="左对齐"
        @click="actions.setAlign('left')"
      >
        ≡
      </button>
      <button
        type="button"
        class="tb-btn"
        :class="{ active: isActive({ textAlign: 'center' }) }"
        title="居中"
        @click="actions.setAlign('center')"
      >
        ≣
      </button>
      <button
        type="button"
        class="tb-btn"
        :class="{ active: isActive({ textAlign: 'justify' }) }"
        title="两端对齐"
        @click="actions.setAlign('justify')"
      >
        ☰
      </button>
      <span class="tb-sep" />
      <button
        type="button"
        class="tb-btn"
        title="撤销 (Ctrl+Z)"
        :disabled="!editor.can().undo()"
        @click="actions.undo"
      >
        ↶
      </button>
      <button
        type="button"
        class="tb-btn"
        title="重做 (Ctrl+Y)"
        :disabled="!editor.can().redo()"
        @click="actions.redo"
      >
        ↷
      </button>
    </div>

    <div class="page-frame">
      <EditorContent :editor="editor" class="docx-page" />
    </div>
  </div>
</template>

<style scoped>
.rich-editor {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  align-items: center;
  padding: 6px 10px;
  border: 1px solid #e4e9f2;
  border-radius: 8px;
  background: #fafbfd;
  position: sticky;
  top: 56px;
  z-index: 5;
}

.tb-btn {
  min-width: 32px;
  height: 28px;
  padding: 0 8px;
  border: 1px solid transparent;
  border-radius: 4px;
  background: transparent;
  color: #1d2b4f;
  cursor: pointer;
  font-size: 13px;
  line-height: 1;
}

.tb-btn:hover:not(:disabled) {
  background: #eaf2ff;
}

.tb-btn.active {
  background: #d9e8ff;
  border-color: #2459a9;
  color: #2459a9;
}

.tb-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.tb-sep {
  width: 1px;
  height: 18px;
  background: #d6dde8;
  margin: 0 4px;
}

.page-frame {
  display: flex;
  justify-content: center;
}

.docx-page {
  background: #fff;
  width: 100%;
  max-width: 210mm;
  min-height: 297mm;
  padding: 28mm 25mm;
  border: 1px solid #e4e9f2;
  border-radius: 6px;
  box-shadow: 0 6px 20px rgba(36, 89, 169, 0.08);
  font-family: '仿宋_GB2312', '仿宋', 'Times New Roman', serif;
  font-size: 12pt;
  line-height: 1.5;
  color: #000;
  outline: none;
}

:deep(.docx-prose) {
  outline: none;
  min-height: calc(297mm - 56mm);
}

:deep(.docx-prose p) {
  margin: 0 0 8px;
  text-indent: 2em;
}

:deep(.docx-prose h1) {
  font-family: '方正小标宋简体', '黑体', 'Times New Roman', serif;
  font-size: 22pt;
  text-align: center;
  font-weight: bold;
  margin: 0 0 18px;
  text-indent: 0;
}

:deep(.docx-prose h2) {
  font-family: '黑体', 'Times New Roman', serif;
  font-size: 14pt;
  font-weight: bold;
  margin: 18px 0 10px;
  text-indent: 0;
}

:deep(.docx-prose ul),
:deep(.docx-prose ol) {
  padding-left: 2em;
  margin: 6px 0 8px;
}

:deep(.docx-prose li) {
  margin: 2px 0;
}

:deep(.docx-prose li > p) {
  text-indent: 0;
}

:deep(.docx-prose strong) {
  font-weight: bold;
}

:deep(.docx-table) {
  border-collapse: collapse;
  table-layout: fixed;
  width: 100%;
  margin: 8px 0;
}

:deep(.docx-table th),
:deep(.docx-table td) {
  border: 1px solid #1d2b4f;
  padding: 6px 8px;
  vertical-align: top;
}

:deep(.docx-table th) {
  background: #f0f4fa;
  font-weight: bold;
  text-align: center;
}
</style>