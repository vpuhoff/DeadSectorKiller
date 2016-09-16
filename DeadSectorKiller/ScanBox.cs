using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Drawing;
using System.Data;
using System.Linq;
using System.Text;
using System.Windows.Forms;
using System.IO;
using System.Threading.Tasks;
using System.Security.Cryptography;

namespace DeadSectorKiller
{
    public partial class ScanBox : UserControl
    {
        public string scandrive;
        string sample;
        string samplemd5;
        string tempdir;
        int i = 0;
        long free;
        byte[] samplefile;
        Random rnd = new Random();
        private int cntn;
        public ScanBox()
        {
            InitializeComponent();
        }

        public async void StartScan(string drive,int fragmentcnt=500)
        {
            scandrive = drive[0].ToString();
            tempdir = drive;
            init(fragmentcnt);
           
            await StageOnePrepairDrive();
            await CheckFiles();
        }

        void init(int fragmentcnt = 500)
        {
            scandrive = tempdir[0].ToString();
            free = GetTotalFreeSpace(scandrive);
            sample = Path.GetTempFileName();
            using (var fs = new FileStream(sample, FileMode.Create, FileAccess.Write, FileShare.None))
            {
                int psize = (int)Math.Ceiling((double)(free / fragmentcnt));
                fs.SetLength(psize);
                samplefile = new byte[psize];
                rnd.NextBytes(samplefile);
                fs.Write(samplefile, 0, samplefile.Length );
            }
            samplefile = File.ReadAllBytes(sample);
            
            samplemd5 = GetMD5(sample);
            
            double cnt = free / GetFileSize(sample);
            cnt = Math.Ceiling(cnt);
            cntn = (int)cnt;
            pb1.Maximum = cntn;
            pb2.Maximum = cntn;
            pb3.Maximum = cntn * 2;
            p1 = 0;
            p2 = 0;
            p3 = 0;
            plotBox1.CreateBox(cntn);
        }

        private long GetFileSize(string filename)
        {
            FileInfo f = new FileInfo(filename);
            long s1 = f.Length;
            return s1;
        }
        private long GetTotalFreeSpace(string driveName)
        {
            foreach (DriveInfo drive in DriveInfo.GetDrives())
            {
                if (drive.IsReady && drive.Name == driveName + ":\\")
                {
                    return drive.AvailableFreeSpace ;
                }
            }
            return -1;
        }

        async Task<DateTime> StageOnePrepairDrive()
        {
           
            await Task.Run(() =>
            {
                int max = 20;
                int aver = 20;
                files = new List<string>();
                files2 = new List<string>();
                for (int j = 0; j < cntn; j++)
                {
                    string newfn = tempdir + Guid.NewGuid().ToString();
                    using (var fs = new FileStream(newfn + ".tf", FileMode.Create, FileAccess.Write, FileShare.None))
                    {
                        try
                        {
                            fs.SetLength(samplefile.Length);
                            files.Add(newfn + ".tf");
                        }
                        catch (Exception ee)
                        {
                            cntn = j;
                            break;
                        }
                    }
                    
                    p1++;
                }
                p1 = 0;
                BeginInvoke(new MethodInvoker(delegate { 
                    pb1.Maximum = pb2.Maximum = cntn; 
                    pb3.Maximum = cntn * 2; 
                    plotBox1.CreateBox(cntn); 
                }));
                for (int j = 0; j < cntn; j++)
                {
                    string newfn = files[j];
                    DateTime dt1 = DateTime.Now;
                    
                    bool error = false;
                    try
                    {
                        //File.WriteAllBytes(newfn + ".tf", samplefile);
                        using (var fs = new FileStream(newfn , FileMode.Create, FileAccess.Write, FileShare.None))
                        {
                            fs.Write(samplefile, 0, samplefile.Length);
                        }
                        File.Move(newfn , newfn + ".ready");
                        files2.Add(newfn + ".ready");
                    }
                    catch (Exception)
                    {
                        try
                        {
                            File.Move(newfn + ".ready", newfn + ".bad");
                        }
                        catch (Exception)
                        {
                            try
                            {
                                File.Move(newfn, newfn + ".bad");
                            }
                            catch (Exception)
                            {
                            }
                        }
                        error = true;
                        bad++;
                    }

                    DateTime dt2 = DateTime.Now;
                    var sp = dt2 - dt1;
                    if (sp.TotalSeconds > aver)
                    {
                        File.Move(newfn + ".ready", newfn + ".timeout");
                        error = true;
                        slow++;
                    }
                    if (sp.TotalSeconds < 15)
                    {
                        aver = aver + (int)sp.TotalSeconds;
                        aver = aver / 2;
                        aver = aver + 3;
                    }

                    if (error == false)
                    {
                        good++;
                    }

                   

                    if (error )
	                {
                        InvokeSetColor(p1, Color.OrangeRed );
	                }else
	                {
                        InvokeSetColor(p1, Color.BlueViolet );
	                }
                    p1++;
                    p3++;
                }
            });
            return DateTime.Now;
        }

        void InvokeSetColor(int n, Color c)
        {
            BeginInvoke(new MethodInvoker(delegate { plotBox1.SetColor(n, c); }));
        }

        int good = 0;
        int bad = 0;
        int slow=0;

        List<string> files;
        List<string> files2;
        private async Task<DateTime> CheckFiles()
        {
            await Task.Run(() =>
            {
                foreach (var item in files2)
                {
                    bool error = false;
                    string newfn = item;

                    try
                    {
                        string md5 = GetMD5(newfn);
                        if (md5 != samplemd5)
                        {
                            File.Move(newfn, newfn + ".bad");
                            error = true;
                            bad++;
                        }
                        else { File.Move(newfn, newfn + ".good"); }

                    }
                    catch (Exception)
                    {
                        File.Move(newfn, newfn + ".verybad");
                        error = true;
                        bad++;
                    }
                    p2++;
                    p3++;
                    if (!error)
                    {
                        good++;
                    }
                    if (error)
                    {
                        InvokeSetColor(p2, Color.PaleVioletRed );
                    }
                    else
                    {
                        InvokeSetColor(p2, Color.LimeGreen );
                    }
                }
                MessageBox.Show("Check is complete, you can remove *.good files from selected drive.");
            });
            return DateTime.Now;
        }

        int pp1, pp2, pp3 = 0;
        public int p1
        {
            get { return pp1; }
            set
            {
                try
                {
                    BeginInvoke(new MethodInvoker(delegate { pp1 = value; pb1.Value = value; }));
                }
                catch (Exception)
                {
                    
                } 
            }
        }
        public int p2
        {
            get { return pp2; }
            set
            {
                try
                {
                    BeginInvoke(new MethodInvoker(delegate { pp2 = value; pb2.Value = value; }));
                }
                catch (Exception)
                {
                    
                } 
            }
        }
        public int p3
        {
            get { return pp3; }
            set
            {
                try
                {
                    BeginInvoke(new MethodInvoker(delegate { pp3 = value; pb3.Value = value; }));
                }
                catch (Exception)
                {
                    
                } 
            }
        }
        string GetMD5(string filename)
        {
            using (var md5 = MD5.Create())
            {
                using (var stream = File.OpenRead(filename))
                {
                    return BitConverter.ToString(md5.ComputeHash(stream)).Replace("-", "").ToLower();
                }
            }
        }
    }
}
