import common from './common';
import nav from './nav';
import schedule from './schedule';
import components from './components';
import misc from './misc';
import finance from './finance';

export const messages = {
  ...common,
  ...nav,
  ...schedule,
  ...components,
  ...misc,
  ...finance,
};

export type MessageKey = keyof typeof messages;
