import js from '@eslint/js'
import { defineConfig } from 'eslint/config'
import jsxA11y from 'eslint-plugin-jsx-a11y'
import reactHooks from 'eslint-plugin-react-hooks'
import globals from 'globals'
import tseslint from 'typescript-eslint'

export default defineConfig(
  { ignores: ['dist', 'node_modules', 'coverage'] },
  js.configs.recommended,
  tseslint.configs.recommended,
  jsxA11y.flatConfigs.recommended,
  reactHooks.configs.flat.recommended,
  {
    languageOptions: { globals: globals.browser },
    rules: {
      'no-eval': 'error',
      'no-implied-eval': 'error',
      'no-new-func': 'error',
      // Server strings (transcripts, LLM output) are untrusted: never render them as HTML.
      'no-restricted-syntax': [
        'error',
        {
          selector: "JSXAttribute[name.name='dangerouslySetInnerHTML']",
          message: 'dangerouslySetInnerHTML is forbidden; render server data as text.',
        },
        {
          selector: 'AssignmentExpression[left.property.name=/^(innerHTML|outerHTML)$/]',
          message: 'innerHTML/outerHTML are forbidden; render server data as text.',
        },
        {
          selector: "CallExpression[callee.property.name='insertAdjacentHTML']",
          message: 'insertAdjacentHTML is forbidden; render server data as text.',
        },
      ],
      // Only the theme preference may touch browser storage.
      'no-restricted-globals': [
        'error',
        { name: 'localStorage', message: 'Browser storage is only allowed in src/lib/theme.ts.' },
        { name: 'sessionStorage', message: 'Browser storage is forbidden (no tokens or PII).' },
      ],
    },
  },
  {
    files: ['src/lib/theme.ts', 'tests/**'],
    rules: { 'no-restricted-globals': ['error', { name: 'sessionStorage' }] },
  },
  { files: ['*.js', '*.ts'], languageOptions: { globals: globals.node } },
)
