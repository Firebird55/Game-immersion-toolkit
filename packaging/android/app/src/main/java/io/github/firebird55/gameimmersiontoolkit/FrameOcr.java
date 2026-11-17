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
        final byte[] bytes;final long generation, sequence;final String locale;
        Frame(byte[] b, long g, long s, String l) { bytes=b;generation=g;sequence=s;locale=l; }
    }
    private final java.util.concurrent.ExecutorService worker = Executors.newSingleThreadExecutor();
    private final AtomicReference<Frame> pending = new AtomicReference<>();
    private final AtomicBoolean active = new AtomicBoolean(false);
    private final HashMap<String, TextRecognizer> models = new HashMap<>();
    private final AccountProtection protectedAccounts;
    private final Context context;
    private NativeX64Decoder dataDecoder;
    private PublisherCrypto publisherCrypto;
    public synchronized PublisherCrypto publisherCrypto() {
        if (publisherCrypto == null) publisherCrypto = new PublisherCrypto(context);
        return publisherCrypto;
    }
    public FrameOcr(Context context) { this.context = context.getApplicationContext();protectedAccounts = new AccountProtection(this.context); }
    public String protect(String encoded, boolean decrypt) { return protectedAccounts.protect(encoded, decrypt); }
    public String protectAuthored(String encoded, boolean decrypt) { return AccountProtection.authored(context).protect(encoded, decrypt); }
    public void assertAuthoredAccounts() { if (!BuildConfig.DEBUG) throw new IllegalStateException(); }
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
        BitmapFactory.Options bounds = dimensions(bytes);
        pending.set(new Frame(bytes, generation, sequence, locale));
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
    private TextRecognizer model(String locale) {
        String script = locale.startsWith("zh") ? "zh" : locale.startsWith("ja") ? "ja" : locale.startsWith("ko") ? "ko" : "latin";
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
        Bitmap bitmap = null;
        try {
            BitmapFactory.Options bounds = new BitmapFactory.Options();bounds.inJustDecodeBounds = true;
            BitmapFactory.decodeByteArray(frame.bytes, 0, frame.bytes.length, bounds);
            if (bounds.outWidth <= 0 || bounds.outHeight <= 0 || bounds.outWidth > 4096 || bounds.outHeight > 4096) return;
            bitmap = BitmapFactory.decodeByteArray(frame.bytes, 0, frame.bytes.length);
            if (bitmap == null) return;
            JSONObject result = recognizeBitmap(bitmap, frame.locale);
            Python.getInstance().getModule("backend.android_host").callAttr("accept_ocr", frame.generation, frame.sequence, result.toString());
        } catch (Exception error) {
            if (BuildConfig.DEBUG) android.util.Log.w("ToolkitAndroid", "A frame could not be recognized locally");
        } finally { if (bitmap != null) bitmap.recycle(); }
    }
    private synchronized JSONObject recognizeBitmap(Bitmap bitmap, String locale) throws Exception {
            Text text = Tasks.await(model(locale).process(InputImage.fromBitmap(bitmap, 0)), 30, TimeUnit.SECONDS);
            JSONArray blocks = new JSONArray(), presentationLines = new JSONArray();
            boolean presentationComplete = true;
            if (text.getTextBlocks().size() > 128) throw new IllegalArgumentException();
            for (Text.TextBlock block : text.getTextBlocks()) {
                Rect r = block.getBoundingBox();
                if (r == null || block.getText().length() > 8192) continue;
                JSONObject item = new JSONObject();item.put("text", block.getText());
                item.put("rect", new JSONArray(new int[]{r.left, r.top, r.right, r.bottom}));blocks.put(item);
                for (Text.Line line : block.getLines()) {
                    Rect lineRect = line.getBoundingBox();
                    if (presentationLines.length() >= 512 || line.getText().length() > 2048 || lineRect == null
                            || lineRect.left < 0 || lineRect.top < 0 || lineRect.right > bitmap.getWidth()
                            || lineRect.bottom > bitmap.getHeight() || lineRect.width() <= 0 || lineRect.height() <= 0) {
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
            JSONObject result = new JSONObject();result.put("width", bitmap.getWidth());
            result.put("height", bitmap.getHeight());result.put("blocks", blocks);
            result.put("presentation_lines", presentationComplete ? presentationLines : new JSONArray());
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
}
