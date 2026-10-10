import common from './common';
import nav from './nav';
import schedule from './schedule';
import components from './components';
import misc from './misc';
import finance from './finance';
import people from './people';
import attendance from './attendance';
import labels from './labels';
import salaries from './salaries';
import rating from './rating';

export const messages = {
  ...common,
  ...nav,
  ...schedule,
  ...components,
  ...misc,
  ...finance,
  ...people,
  ...attendance,
  ...labels,
  ...salaries,
  ...rating,
};

export type MessageKey = keyof typeof messages;
