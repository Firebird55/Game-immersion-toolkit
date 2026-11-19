package io.github.firebird55.gameimmersiontoolkit;

import android.content.Context;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.Rect;
import com.chaquo.python.Python;
import com.google.android.gms.tasks.Tasks;
import com.google.mlkit.vision.common.InputImage;
import com.google.mlkit.vision.text.Text;
import com.google.mlkit.vision.text.TextRecognition;
import com.google.mlkit.vision.text.TextRecognizer;
import com.google.mlkit.vision.text.latin.TextRecognizerOptions;
import com.google.mlkit.vision.text.chinese.ChineseTextRecognizerOptions;
import com.google.mlkit.vision.text.japanese.JapaneseTextRecognizerOptions;
import com.google.mlkit.vision.text.korean.KoreanTextRecognizerOptions;
import java.util.HashMap;
import java.util.LinkedHashSet;
import java.io.File;
import java.io.ByteArrayOutputStream;
import android.util.Base64;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;
import org.json.JSONArray;
import org.json.JSONObject;

/** Bundled on-device OCR; one worker and only the newest waiting frame. */
public final class FrameOcr {
    private static final class Frame {
        final byte[] bytes;final long generation, sequence;final String locales;final boolean comic;
        Frame(byte[] b, long g, long s, String l, boolean c) { bytes=b;generation=g;sequence=s;locales=l;comic=c; }
    }
    private final java.util.concurrent.ExecutorService worker = Executors.newSingleThreadExecutor();
    private final AtomicReference<Frame> pending = new AtomicReference<>();
    private final AtomicBoolean active = new AtomicBoolean(false);
    private final HashMap<String, TextRecognizer> models = new HashMap<>();
    private final AccountProtection protectedAccounts;
    private final Context context;
    private final PortableSubtitleOcr portable;
    private NativeX64Decoder dataDecoder;
    private PublisherCrypto publisherCrypto;
    private ZzzWemCodec zzzWem;
    public synchronized ZzzWemCodec zzzWemCodec() {
        if (zzzWem == null) zzzWem = new ZzzWemCodec(context);
        return zzzWem;
    }
    private PublisherHash publisherHash;
    private ZzzCatalogueWorker zzzCatalogueWorker;
    public synchronized ZzzCatalogueWorker zzzCatalogueWorker() {
        if (zzzCatalogueWorker == null) zzzCatalogueWorker = new ZzzCatalogueWorker(context);
        return zzzCatalogueWorker;
    }
    public synchronized PublisherHash publisherHash() {
        if (publisherHash == null) publisherHash = new PublisherHash(context);
        return publisherHash;
    }
    public synchronized PublisherCrypto publisherCrypto() {
        if (publisherCrypto == null) publisherCrypto = new PublisherCrypto(context);
        return publisherCrypto;
    }
    public FrameOcr(Context context, File frontend) {
        this.context = context.getApplicationContext();
        protectedAccounts = new AccountProtection(this.context);
        portable = new PortableSubtitleOcr(this.context, frontend);
    }
    public String protect(String encoded, boolean decrypt) { return protectedAccounts.protect(encoded, decrypt); }
    public String protectAuthored(String encoded, boolean decrypt) { return AccountProtection.authored(context).protect(encoded, decrypt); }
    public void assertAuthoredAccounts() { if (!BuildConfig.DEBUG) throw new IllegalStateException(); }
    public void assertAuthoredGameData() { if (!BuildConfig.DEBUG) throw new IllegalStateException(); }
    private synchronized NativeX64Decoder dataDecoder() {
        if (dataDecoder == null) dataDecoder = new NativeX64Decoder(context);
        return dataDecoder;
    }
    public String x64DecoderProof() throws Exception { return dataDecoder().proof(); }
    public String disassembleX64(byte[] data, long address, int count) throws Exception { return dataDecoder().disassemble(data, address, count); }
    private BitmapFactory.Options dimensions(byte[] bytes) {
        if (bytes.length == 0 || bytes.length > 10 * 1024 * 1024) throw new IllegalArgumentException();
        BitmapFactory.Options bounds = new BitmapFactory.Options();bounds.inJustDecodeBounds = true;
        BitmapFactory.decodeByteArray(bytes, 0, bytes.length, bounds);
        if (bounds.outWidth <= 0 || bounds.outHeight <= 0 || bounds.outWidth > 4096 || bounds.outHeight > 4096)
            throw new IllegalArgumentException();
        return bounds;
    }
    public String submit(byte[] bytes, long generation, long sequence, String locale) throws Exception {
        return submitLanguages(bytes, generation, sequence, locale, false);
    }
    public String submitLanguages(byte[] bytes, long generation, long sequence, String locales, boolean comic) throws Exception {
        if (locales.length() > 2048 || !locales.matches("[A-Za-z0-9,-]+")) throw new IllegalArgumentException();
        BitmapFactory.Options bounds = dimensions(bytes);
        pending.set(new Frame(bytes, generation, sequence, locales, comic));
        schedule();
        return new JSONObject().put("width", bounds.outWidth).put("height", bounds.outHeight).toString();
    }
    public String preview(byte[] bytes, int left, int top, int width, int height) {
        BitmapFactory.Options bounds = dimensions(bytes);
        if (left < 0 || top < 0 || width <= 0 || height <= 0
                || (long)left + width > bounds.outWidth || (long)top + height > bounds.outHeight)
            throw new IllegalArgumentException();
        Bitmap source = null, crop = null, scaled = null;
        try {
            source = BitmapFactory.decodeByteArray(bytes, 0, bytes.length);
            if (source == null) throw new IllegalArgumentException();
            crop = Bitmap.createBitmap(source, left, top, width, height);
            double ratio = Math.min(1.0, 1280.0 / Math.max(width, height));
            scaled = Bitmap.createScaledBitmap(crop, Math.max(1, (int)Math.round(width * ratio)),
                Math.max(1, (int)Math.round(height * ratio)), true);
            ByteArrayOutputStream output = new ByteArrayOutputStream();
            if (!scaled.compress(Bitmap.CompressFormat.JPEG, 80, output) || output.size() > 1024 * 1024)
                throw new IllegalArgumentException();
            return Base64.encodeToString(output.toByteArray(), Base64.NO_WRAP);
        } finally {
            if (scaled != null && scaled != crop && scaled != source) scaled.recycle();
            if (crop != null && crop != source) crop.recycle();
            if (source != null) source.recycle();
        }
    }
    public String authoredPreviewProbe(int width, int height, int pictureX, int pictureY,
            int pictureWidth, int pictureHeight, int left, int top, int cropWidth, int cropHeight) throws Exception {
        if (!BuildConfig.DEBUG) throw new IllegalStateException();
        Bitmap bitmap = Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888);
        Bitmap decoded = null;
        try {
            android.graphics.Canvas canvas = new android.graphics.Canvas(bitmap);canvas.drawColor(android.graphics.Color.BLACK);
            android.graphics.Paint paint = new android.graphics.Paint();paint.setColor(android.graphics.Color.BLUE);
            canvas.drawRect(pictureX, pictureY, pictureX + pictureWidth, pictureY + pictureHeight, paint);
            paint.setColor(android.graphics.Color.RED);
            canvas.drawRect(pictureX + pictureWidth / 2, pictureY + pictureHeight / 2,
                pictureX + pictureWidth, pictureY + pictureHeight, paint);
            ByteArrayOutputStream bytes = new ByteArrayOutputStream();bitmap.compress(Bitmap.CompressFormat.PNG, 100, bytes);
            byte[] jpeg = Base64.decode(preview(bytes.toByteArray(), left, top, cropWidth, cropHeight), Base64.NO_WRAP);
            decoded = BitmapFactory.decodeByteArray(jpeg, 0, jpeg.length);
            return new JSONObject().put("width", decoded.getWidth()).put("height", decoded.getHeight())
                .put("first_pixel", decoded.getPixel(0, 0)).put("last_pixel", decoded.getPixel(decoded.getWidth()-1, decoded.getHeight()-1))
                .put("bytes", jpeg.length).toString();
        } finally {if (decoded != null) decoded.recycle();bitmap.recycle();}
    }
    private void schedule() {
        if (active.compareAndSet(false, true)) worker.execute(() -> {
            try {
                Frame frame;
                while ((frame = pending.getAndSet(null)) != null) recognize(frame);
            } finally {
                active.set(false);
                if (pending.get() != null) schedule();
            }
        });
    }
    private static String script(String locale) {
        String language = locale.split("-", 2)[0];
        switch (language) {
            case "zh": case "ja": case "ko": return language;
            case "ru": return "rus";
            case "th": return "tha";
            default: return "latin";
        }
    }
    private TextRecognizer model(String locale) {
        String script = script(locale);
        TextRecognizer result = models.get(script);
        if (result == null) {
            switch (script) {
                case "zh": result = TextRecognition.getClient(new ChineseTextRecognizerOptions.Builder().build());break;
                case "ja": result = TextRecognition.getClient(new JapaneseTextRecognizerOptions.Builder().build());break;
                case "ko": result = TextRecognition.getClient(new KoreanTextRecognizerOptions.Builder().build());break;
                default: result = TextRecognition.getClient(TextRecognizerOptions.DEFAULT_OPTIONS);
            }
            models.put(script, result);
        }
        return result;
    }
    private void recognize(Frame frame) {
        Bitmap bitmap = null, scaled = null;
        try {
            BitmapFactory.Options bounds = new BitmapFactory.Options();bounds.inJustDecodeBounds = true;
            BitmapFactory.decodeByteArray(frame.bytes, 0, frame.bytes.length, bounds);
            if (bounds.outWidth <= 0 || bounds.outHeight <= 0 || bounds.outWidth > 4096 || bounds.outHeight > 4096) return;
            bitmap = BitmapFactory.decodeByteArray(frame.bytes, 0, frame.bytes.length);
            if (bitmap == null) return;
            int width = bitmap.getWidth(), height = bitmap.getHeight();
            double factor = Math.min(2.0, 1600.0 / Math.max(width, height));
            if (frame.comic && factor > 1.0) {
                scaled = Bitmap.createScaledBitmap(bitmap, (int)Math.round(width * factor),
                    (int)Math.round(height * factor), true);
            }
            JSONObject result = recognizeBitmap(scaled == null ? bitmap : scaled, frame.locales, frame.comic, width, height);
            if (frame.comic) result.put("filmstrip_samples", filmstripSamples(bitmap));
            Python.getInstance().getModule("backend.android_host").callAttr("accept_ocr", frame.generation, frame.sequence, result.toString());
        } catch (Exception error) {
            if (BuildConfig.DEBUG) android.util.Log.w("ToolkitAndroid", "A frame could not be recognized locally");
        } finally {
            if (scaled != null && scaled != bitmap) scaled.recycle();
            if (bitmap != null) bitmap.recycle();
        }
    }

    private static JSONArray filmstripSamples(Bitmap bitmap) {
        JSONArray rows = new JSONArray();
        for (int offset : new int[]{3, 5, 7, 91, 93, 95}) {
            JSONArray row = new JSONArray();
            int y = offset * bitmap.getHeight() / 100;
            for (int x = 0; x < 256; x++) {
                int rgb = bitmap.getPixel(x * (bitmap.getWidth() - 1) / 255, y);
                int luma = (((rgb >> 16) & 255) * 299 + ((rgb >> 8) & 255) * 587 + (rgb & 255) * 114 + 500) / 1000;
                row.put(luma);
            }
            rows.put(row);
        }
        return rows;
    }
    private synchronized JSONObject recognizeBitmap(Bitmap bitmap, String locale) throws Exception {
        return recognizeBitmap(bitmap, locale, false, bitmap.getWidth(), bitmap.getHeight());
    }
    private synchronized JSONObject recognizeBitmap(Bitmap bitmap, String locales, boolean comic, int width, int height) throws Exception {
        InputImage image = InputImage.fromBitmap(bitmap, 0);
        LinkedHashSet<String> scripts = new LinkedHashSet<>();
        for (String locale : locales.split(",")) scripts.add(script(locale));
        JSONObject result = null;
        JSONArray alternatives = new JSONArray();
        for (String script : scripts) {
            try {
                JSONObject recognized;
                if ("rus".equals(script) || "tha".equals(script))
                    recognized = portable.recognize(bitmap, script, width, height);
                else {
                    Text text = Tasks.await(model(script).process(image), 30, TimeUnit.SECONDS);
                    recognized = describe(text, bitmap, width, height, comic);
                }
                if (result == null) result = recognized;
                else alternatives.put(recognized);
            } catch (InterruptedException error) { throw error; }
            catch (Exception error) {
                if (BuildConfig.DEBUG) android.util.Log.w("ToolkitAndroid", "A prepared subtitle script could not be read locally");
            }
        }
        if (result == null) throw new IllegalStateException("No subtitle OCR result");
        if (alternatives.length() > 0) result.put("alternates", alternatives);
        return result;
    }
    private static Rect originalRect(Rect rect, Bitmap bitmap, int width, int height) {
        int inputWidth = bitmap.getWidth(), inputHeight = bitmap.getHeight();
        if (rect == null || rect.left < 0 || rect.top < 0 || rect.right > inputWidth || rect.bottom > inputHeight
                || rect.width() <= 0 || rect.height() <= 0) return null;
        return new Rect(rect.left * width / inputWidth, rect.top * height / inputHeight,
            (rect.right * width + inputWidth - 1) / inputWidth, (rect.bottom * height + inputHeight - 1) / inputHeight);
    }
    private JSONObject describe(Text text, Bitmap bitmap, int width, int height, boolean keepPartial) throws Exception {
            JSONArray blocks = new JSONArray(), presentationLines = new JSONArray();
            boolean presentationComplete = true;
            if (text.getTextBlocks().size() > 128) throw new IllegalArgumentException();
            for (Text.TextBlock block : text.getTextBlocks()) {
                Rect r = originalRect(block.getBoundingBox(), bitmap, width, height);
                if (r != null && block.getText().length() <= 8192) {
                    JSONObject item = new JSONObject();item.put("text", block.getText());
                    item.put("rect", new JSONArray(new int[]{r.left, r.top, r.right, r.bottom}));blocks.put(item);
                } else if (!keepPartial) continue;
                for (Text.Line line : block.getLines()) {
                    Rect lineRect = originalRect(line.getBoundingBox(), bitmap, width, height);
                    if (presentationLines.length() >= 512 || line.getText().length() > 2048 || lineRect == null) {
                        presentationComplete = false;continue;
                    }
                    float confidence = line.getConfidence();
                    if (!Float.isFinite(confidence) || confidence < 0 || confidence > 1 || line.getElements().isEmpty()) confidence = 0;
                    for (Text.Element element : line.getElements()) {
                        float score = element.getConfidence();
                        confidence = !Float.isFinite(score) || score < 0 || score > 1 ? 0 : Math.min(confidence, score);
                    }
                    JSONObject rectangle = new JSONObject().put("x1", lineRect.left).put("y1", lineRect.top)
                        .put("x2", lineRect.right).put("y2", lineRect.top).put("x3", lineRect.right)
                        .put("y3", lineRect.bottom).put("x4", lineRect.left).put("y4", lineRect.bottom);
                    presentationLines.put(new JSONObject().put("text", line.getText()).put("confidence", confidence)
                        .put("bounding_rect", rectangle));
                }
            }
            JSONObject result = new JSONObject();result.put("width", width);
            result.put("height", height);result.put("blocks", blocks);
            result.put("presentation_lines", presentationComplete || keepPartial ? presentationLines : new JSONArray());
            return result;
    }
    public String authoredProbe() throws Exception {
        if (!BuildConfig.DEBUG) throw new IllegalStateException();
        Bitmap bitmap = Bitmap.createBitmap(1600, 240, Bitmap.Config.ARGB_8888);
        try {
            android.graphics.Canvas canvas = new android.graphics.Canvas(bitmap);
            canvas.drawColor(android.graphics.Color.BLACK);
            android.graphics.Paint paint = new android.graphics.Paint(android.graphics.Paint.ANTI_ALIAS_FLAG);
            paint.setColor(android.graphics.Color.WHITE);paint.setTextSize(64);
            canvas.drawText("Follow the river beyond the bridge.", 40, 140, paint);
            return recognizeBitmap(bitmap, "en").toString();
        } finally {bitmap.recycle();}
    }

    public JSONObject authoredSubtitleScripts() throws Exception {
        if (!BuildConfig.DEBUG) throw new IllegalStateException();
        JSONObject result = new JSONObject();
        for (String[] sample : new String[][]{
                {"ru", "Мост закрыт"},
                {"th", "สะพานปิด"}
        }) {
            Bitmap bitmap = Bitmap.createBitmap(1240, 210, Bitmap.Config.ARGB_8888);
            try {
                android.graphics.Canvas canvas = new android.graphics.Canvas(bitmap);
                canvas.drawColor(android.graphics.Color.WHITE);
                android.graphics.Paint paint = new android.graphics.Paint(android.graphics.Paint.ANTI_ALIAS_FLAG);
                paint.setColor(android.graphics.Color.BLACK);
                paint.setTextSize(64);
                canvas.drawText(sample[1], 38, 140, paint);
                JSONObject observed = recognizeBitmap(bitmap, sample[0]);
                JSONArray blocks = observed.getJSONArray("blocks");
                StringBuilder text = new StringBuilder();
                for (int i = 0; i < blocks.length(); i++) text.append(blocks.getJSONObject(i).getString("text"));
                result.put(sample[0], normalizedProbeText(sample[1]).equals(normalizedProbeText(text.toString())));
            } finally {bitmap.recycle();}
        }
        return result;
    }

    private static String normalizedProbeText(String text) {
        return java.text.Normalizer.normalize(text, java.text.Normalizer.Form.NFKC)
            .toLowerCase(java.util.Locale.ROOT).replaceAll("[^\\p{L}\\p{N}]", "");
    }
}
