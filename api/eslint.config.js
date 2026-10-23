import js from '@eslint/js';
import globals from 'globals';

export default [
  js.configs.recommended,
  {
    languageOptions: { ecmaVersion: 'latest', sourceType: 'module', globals: { ...globals.node } },
    rules: {
      // Express error handlers are identified by arity, so `next` must stay in the signature.
      'no-unused-vars': ['error', { argsIgnorePattern: '^(next|_)', ignoreRestSiblings: true }],
      'no-control-regex': 'off',
      eqeqeq: 'error',
    },
  },
];
