/** Source word boundaries only affect line wrapping, never token lookup offsets. */
export declare function readingWordRanges(text: string): {
    start: number;
    end: number;
}[];
/** Keep original provider spans intact and attach closing punctuation to them. */
export declare function readingWrapRanges(text: string, tokens: readonly {
    start: number;
    end: number;
}[]): {
    start: number;
    end: number;
}[];
