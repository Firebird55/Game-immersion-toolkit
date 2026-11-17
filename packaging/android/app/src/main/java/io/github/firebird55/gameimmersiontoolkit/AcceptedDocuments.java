package io.github.firebird55.gameimmersiontoolkit;

import java.util.LinkedHashSet;
import java.util.Locale;

/** The two document formats supported by the shared import controls. */
final class AcceptedDocuments {
    static String[] mimeTypes(String[] accepts) {
        if (accepts == null || accepts.length == 0 || accepts.length > 16) return new String[0];
        LinkedHashSet<String> result = new LinkedHashSet<>();
        int length = 0;
        for (String accept : accepts) {
            if (accept == null || (length += accept.length()) > 1024) return new String[0];
            for (String raw : accept.split(",", -1)) {
                String value = raw.trim().toLowerCase(Locale.ROOT);
                if (value.equals(".zip") || value.equals("application/zip") || value.equals("application/x-zip-compressed"))
                    result.add("application/zip");
                else if (value.equals(".json") || value.equals("application/json")) result.add("application/json");
                else return new String[0];
            }
        }
        return result.toArray(new String[0]);
    }
}
