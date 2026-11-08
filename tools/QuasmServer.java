import java.io.BufferedInputStream;
import java.io.ByteArrayOutputStream;
import java.io.DataInputStream;
import java.io.FileDescriptor;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.io.PrintStream;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;

import rars.api.Options;
import rars.api.Program;
import rars.simulator.Simulator;

/**
 * Assembles the QuAsm interpreter once and runs many programs through it in
 * one JVM, through the same RARS simulator the command line uses. A cold JVM
 * plus assembling ~3,000 lines costs seconds per run, which is what made the
 * suite take 19 minutes; here that is paid once per process.
 *
 * Every run starts from the freshly assembled image: Program.setup() restores
 * memory and registers, so no register, variable or PRNG state leaks from one
 * program into the next. tools/rars_server.py checks this before trusting it.
 *
 * Protocol, one request at a time over stdin/stdout: the client writes a line
 * holding a byte count (and, optionally, a step cap for this run alone), then
 * that many bytes of UTF-8 program text; the server
 * answers with a line "<reason> <byte count>", then that many bytes of the
 * interpreter's output. The reason is RARS's own: NORMAL_TERMINATION,
 * MAX_STEPS, EXCEPTION, and so on.
 *
 *     java -cp rars1_6.jar:. QuasmServer main.s [maxSteps]
 */
public class QuasmServer {
    public static void main(String[] args) throws Exception {
        String mainFile = args[0];
        Options opt = new Options();
        int defaultSteps = args.length > 1 ? Integer.parseInt(args[1]) : 200_000_000;
        opt.maxSteps = defaultSteps;

        // RARS may print to System.out on its own; keep the protocol channel clean.
        OutputStream wire = new FileOutputStream(FileDescriptor.out);
        System.setOut(new PrintStream(new FileOutputStream(FileDescriptor.err), true));

        Program prog = new Program(opt);
        ArrayList<String> files = new ArrayList<>();
        files.add(mainFile);
        try {
            prog.assemble(files, mainFile);
        } catch (rars.AssemblyException e) {
            System.err.println(e.errors().generateErrorAndWarningReport());
            System.exit(2);
        }
        disableBackstepping(prog);

        DataInputStream in = new DataInputStream(new BufferedInputStream(System.in));
        while (true) {
            String header = readLine(in);
            if (header == null) {
                break;
            }
            String[] fields = header.trim().split(" ");
            int n = Integer.parseInt(fields[0]);
            // An optional second field caps this one run's steps; RARS reads
            // the cap from the Options object on every simulate().
            opt.maxSteps = fields.length > 1 ? Integer.parseInt(fields[1]) : defaultSteps;
            byte[] body = in.readNBytes(n);
            prog.setup(new ArrayList<>(), new String(body, StandardCharsets.UTF_8));
            String reason;
            try {
                Simulator.Reason r = prog.simulate();
                reason = r.name();
            } catch (rars.SimulationException e) {
                reason = "EXCEPTION";
            }
            byte[] out = (prog.getSTDOUT() + prog.getSTDERR()).getBytes(StandardCharsets.UTF_8);
            wire.write((reason + " " + out.length + "\n").getBytes(StandardCharsets.UTF_8));
            wire.write(out);
            wire.flush();
        }
    }

    /**
     * RARS records an undo entry for every register and memory write so that
     * its GUI can step backwards. Nothing here ever steps back, and the
     * recording is most of the per-instruction cost, so it is switched off.
     * rars.api.Program keeps its RISCVprogram private, hence the reflection.
     */
    private static void disableBackstepping(Program prog) throws Exception {
        java.lang.reflect.Field f = Program.class.getDeclaredField("code");
        f.setAccessible(true);
        rars.RISCVprogram code = (rars.RISCVprogram) f.get(prog);
        if (code.getBackStepper() != null) {
            code.getBackStepper().setEnabled(false);
        }
    }

    private static String readLine(InputStream in) throws IOException {
        ByteArrayOutputStream b = new ByteArrayOutputStream();
        int c;
        while ((c = in.read()) != -1 && c != '\n') {
            b.write(c);
        }
        if (c == -1 && b.size() == 0) {
            return null;
        }
        return b.toString(StandardCharsets.UTF_8);
    }
}
