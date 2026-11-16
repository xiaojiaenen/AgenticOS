/**
 * 工具分类表（AgentEditor 与 AgentToolsPanel 共用）。
 *
 * 为什么抽成模块：两处都要展示同一批工具，分类表各写一份必然漂移 ——
 * 新增工具只在一处登记，另一处就落到「其他」。这里作为唯一事实源。
 *
 * 维护约定：新增工具时把它加进对应类别；**忘了加也不会丢**，会归到
 * 「其他」并排在最后，所以不会出现「工具凭空消失」。
 */

export const TOOL_CATEGORIES: Record<string, string[]> = {
  基础能力: ['calc', 'time', 'decision'],
  文件与代码: ['file', 'file_to_md', 'python', 'git'],
  知识与记忆: ['knowledge', 'memory', 'skill'],
  邮件与通知: ['email'],
  数据与图表: ['analyze_data', 'render_chart', 'analyze_template'],
  演示文稿: [
    'save_slide', 'save_slides_batch', 'read_slide', 'batch_edit_slides',
    'submit_slide_plan', 'submit_spec_lock', 'calc_chart_positions', 'check_svg_quality',
    'convert_pptx_to_svg', 'import_pptx_template', 'resume_ppt', 'check_ppt_progress',
    'read_notes',
    // 从 ppt-master 吸收的内容能力（风格/公式/排版/图表选型）
    'list_visual_styles', 'validate_formula', 'measure_text_fit', 'find_chart_template',
  ],
  图片与图标: ['search_images', 'get_image_info', 'search_icons', 'list_icons'],
  网站与部署: [
    'copy_template', 'check_website_project', 'build_website', 'deploy_website', 'npm',
    'apply_design_theme', 'list_design_themes',
  ],
  办公文档: [
    'create_workbook', 'set_range', 'set_formula', 'read_range', 'set_layout', 'build_sheet',
    'create_document', 'set_document_text', 'read_document', 'build_document',
    'batch_edit_slides_office',
  ],
  外部系统与工作流: ['run_workflow'],
};

const TOOL_CATEGORY_OF: Map<string, string> = (() => {
  const map = new Map<string, string>();
  for (const [category, tools] of Object.entries(TOOL_CATEGORIES)) {
    for (const tool of tools) map.set(tool, category);
  }
  return map;
})();

/** 工具所属类别；未登记的一律「其他」（不会丢失）。 */
export function categoryOf(toolName: string): string {
  return TOOL_CATEGORY_OF.get(toolName) ?? '其他';
}

/**
 * 把工具列表按类别分组，保持 TOOL_CATEGORIES 的声明顺序，「其他」恒垫底。
 */
export function groupToolsByCategory<T extends { name: string }>(
  items: T[],
): [string, T[]][] {
  const map = new Map<string, T[]>();
  for (const item of items) {
    const category = categoryOf(item.name);
    const bucket = map.get(category) ?? [];
    bucket.push(item);
    map.set(category, bucket);
  }
  const order = [...Object.keys(TOOL_CATEGORIES), '其他'];
  return [...map.entries()].sort((a, b) => {
    const ia = order.indexOf(a[0]);
    const ib = order.indexOf(b[0]);
    return (ia < 0 ? order.length : ia) - (ib < 0 ? order.length : ib);
  });
}
