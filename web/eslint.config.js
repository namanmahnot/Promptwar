import js from '@eslint/js';
import jsxA11y from 'eslint-plugin-jsx-a11y';
import react from 'eslint-plugin-react';
import reactHooks from 'eslint-plugin-react-hooks';
import globals from 'globals';

export default [
  { ignores: ['dist', 'coverage'] },
  js.configs.recommended,
  react.configs.flat.recommended,
  react.configs.flat['jsx-runtime'],
  jsxA11y.flatConfigs.strict,
  {
    files: ['**/*.{js,jsx}'],
    languageOptions: { ecmaVersion: 'latest', sourceType: 'module', globals: { ...globals.browser } },
    settings: { react: { version: 'detect' } },
    plugins: { 'react-hooks': reactHooks },
    rules: {
      ...reactHooks.configs.recommended.rules,
      'react/prop-types': 'off',
      'react/no-danger': 'error',
      // Scrollable regions must be keyboard-focusable (axe: scrollable-region-focusable).
      'jsx-a11y/no-noninteractive-tabindex': ['error', { roles: ['region'] }],
      'no-unused-vars': ['error', { argsIgnorePattern: '^_' }],
    },
  },
  {
    files: ['src/test/**', '*.config.js'],
    languageOptions: { globals: { ...globals.node } },
  },
];
