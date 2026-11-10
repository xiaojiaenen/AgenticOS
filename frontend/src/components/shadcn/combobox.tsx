/**
 * 可搜索单选组合框。
 *
 * 为什么不用 shadcn 的 Select：模型名动辄几十上百个，不可搜索的下拉只能靠
 * 滚。这里基于**已装好的** cmdk（`command.tsx`）+ Radix Popover 组合，
 * 不引入新依赖。
 *
 * 交互规格对齐 `ui/AgentSelector.tsx`（同样是自研 listbox）：点外部关闭、
 * Esc 关闭、方向键移动、Enter 选中。cmdk 自带键盘处理与 `aria-*`，所以
 * 这里只负责「开合 + 回显」。
 */
import * as React from 'react';
import { Check, ChevronsUpDown } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Button } from './button';
import { Popover, PopoverContent, PopoverTrigger } from './popover';
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from './command';

export type ComboboxOption = {
  value: string;
  label: string;
  /** 次要说明，显示在右侧（如 task_type） */
  hint?: string;
  /** 该选项是否不可选（例如已下架） */
  disabled?: boolean;
};

export type ComboboxProps = {
  options: ComboboxOption[];
  value: string;
  onValueChange: (value: string) => void;
  placeholder?: string;
  searchPlaceholder?: string;
  emptyText?: string;
  /** 触发器额外类名 */
  className?: string;
  disabled?: boolean;
  /** 允许输入不在列表里的值（自由文本）。用于「新建提供商时还没目录」的场景。 */
  allowCustom?: boolean;
  id?: string;
  'aria-label'?: string;
};

export function Combobox({
  options,
  value,
  onValueChange,
  placeholder = '请选择',
  searchPlaceholder = '搜索…',
  emptyText = '没有匹配项',
  className,
  disabled = false,
  allowCustom = false,
  id,
  'aria-label': ariaLabel,
}: ComboboxProps) {
  const [open, setOpen] = React.useState(false);
  const [search, setSearch] = React.useState('');

  const selected = options.find((o) => o.value === value);
  // 自由输入模式下，值不在列表里也要能回显（否则新建态输入的内容看不见）
  const displayText = selected?.label ?? (allowCustom ? value : '');

  const trimmed = search.trim();
  const canUseCustom =
    allowCustom && trimmed.length > 0 && !options.some((o) => o.value === trimmed);

  const commit = (next: string) => {
    onValueChange(next);
    setOpen(false);
    setSearch('');
  };

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          id={id}
          type="button"
          variant="outline"
          role="combobox"
          aria-expanded={open}
          aria-label={ariaLabel}
          disabled={disabled}
          className={cn(
            'h-9 w-full justify-between px-3 text-left text-sm font-normal',
            !displayText && 'text-[var(--muted-foreground)]',
            className,
          )}
        >
          <span className="truncate">{displayText || placeholder}</span>
          <ChevronsUpDown className="ml-2 h-3.5 w-3.5 shrink-0 opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent
        align="start"
        sideOffset={6}
        className="w-[var(--radix-popover-trigger-width)] min-w-56 p-0"
      >
        <Command shouldFilter>
          <CommandInput
            placeholder={searchPlaceholder}
            value={search}
            onValueChange={setSearch}
          />
          <CommandList>
            <CommandEmpty>
              {canUseCustom ? (
                <button
                  type="button"
                  onClick={() => commit(trimmed)}
                  className="w-full rounded-md px-2 py-1.5 text-left text-xs font-medium text-[var(--foreground)] hover:bg-[var(--surface-2)]"
                >
                  使用「{trimmed}」
                </button>
              ) : (
                emptyText
              )}
            </CommandEmpty>
            <CommandGroup>
              {options.map((option) => (
                <CommandItem
                  key={option.value}
                  value={option.value}
                  keywords={[option.label, option.hint ?? '']}
                  disabled={option.disabled}
                  onSelect={() => commit(option.value)}
                  className="gap-2"
                >
                  <Check
                    className={cn(
                      'h-3.5 w-3.5 shrink-0',
                      value === option.value ? 'opacity-100' : 'opacity-0',
                    )}
                  />
                  <span className="min-w-0 flex-1 truncate">{option.label}</span>
                  {option.hint ? (
                    <span className="shrink-0 text-[10px] font-medium text-[var(--muted-foreground)]">
                      {option.hint}
                    </span>
                  ) : null}
                </CommandItem>
              ))}
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}
