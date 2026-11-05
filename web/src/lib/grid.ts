import {
  CellStyleModule,
  ClientSideRowModelModule,
  ColumnApiModule,
  CsvExportModule,
  DateFilterModule,
  ExternalFilterModule,
  type Module,
  ModuleRegistry,
  NumberFilterModule,
  QuickFilterModule,
  RowApiModule,
  TextFilterModule,
  TooltipModule,
  ValidationModule,
  themeQuartz,
} from "ag-grid-community";

// Only the Community modules Kweli uses, so the bundle stays small.
const modules: Module[] = [
  ClientSideRowModelModule,
  CellStyleModule,
  TooltipModule,
  RowApiModule,
  ColumnApiModule,
  QuickFilterModule,
  ExternalFilterModule,
  TextFilterModule,
  NumberFilterModule,
  DateFilterModule,
  CsvExportModule,
];
if (import.meta.env.DEV) modules.push(ValidationModule);
ModuleRegistry.registerModules(modules);

export const kweliGridTheme = themeQuartz.withParams({
  fontFamily: "inherit",
  fontSize: 15,
  backgroundColor: "var(--surface)",
  foregroundColor: "var(--ink)",
  headerBackgroundColor: "var(--paper)",
  headerTextColor: "var(--ink-soft)",
  headerFontWeight: 600,
  borderColor: "var(--line)",
  rowBorder: { color: "var(--line)" },
  accentColor: "var(--focus)",
  oddRowBackgroundColor: "var(--surface)",
  rowHoverColor: "color-mix(in srgb, var(--seal) 6%, transparent)",
  wrapperBorder: false,
  wrapperBorderRadius: 0,
  spacing: 7,
});
