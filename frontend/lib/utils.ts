import { createCn } from "cn/config";

/** Named font sizes from the type scale in app/globals.css (`--text-*`). The merger has to
 *  know they are font sizes: otherwise `text-ui text-muted-foreground` looks like two text
 *  colors and the size is dropped. */
export const TYPE_SCALE = ["micro", "caption", "meta", "small", "ui", "body", "ui-lg", "reading"];

export const cn = createCn({
  extend: { classGroups: { "font-size": [{ text: TYPE_SCALE }] } },
});
